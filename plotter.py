"""
plotter.py  -  a Python turtle that can also drive a real pen.

Student code looks exactly like normal turtle code:

    from plotter import Plotter
    t = Plotter()            # screen only (default)
    t.forward(100)
    t.left(90)
    ...
    t.save_svg("mine.svg")   # for the laser / Cricut
    t.save_gcode("mine.gcode")  # for a USB stick in the printer

To draw live on the Prusa MINI, plug in the USB cable and either:

    t = Plotter(live=True)   # connects at startup
or
    t.connect()              # connect later, then keep drawing

Every movement goes through _goto(), so forward(), backward(), goto(),
setpos(), home(), and circle() all reach the pen.  Moves are sent in the
exact order the student's code runs them, one at a time, and the module
waits for each move to finish before continuing.  Nothing is reordered.

Coordinate system
-----------------
* Turtle units:   1 unit = SCALE mm (default 0.25 mm), origin at the
                  centre of the paper, same as a normal turtle window.
* Paper:          a PAPER_MM square (default 150 mm) centred on the bed.
* Printer:        Prusa MINI bed is 180 x 180 mm.  Bed centre = (90, 90).
* The pen sits beside the nozzle, so PEN_OFFSET (dx, dy) is added when
  converting pen coordinates to nozzle coordinates.

Run  `python plotter.py --ports`  to list serial ports.
Run  `python plotter.py --jog`    to connect, home, and jog Z by hand
                                  while you find your pen heights.
"""

import json
import os
import sys
import time
import turtle

try:
    import serial
    from serial.tools import list_ports
except ImportError:          # pyserial not installed: screen/export only
    serial = None
    list_ports = None

PRUSA_VID = 0x2C99           # Prusa Research USB vendor id
CONFIG_NAME = "plotter_config.json"   # sits next to this file

SERIAL_TIMEOUT = 2           # seconds to wait for one line of reply
SERIAL_TIMEOUT_LONG = 30     # seconds to wait for one command to finish


class PlotterError(Exception):
    """Something went wrong that we can explain in plain English.

    These are printed as a short message rather than a traceback, so that a
    student sees "the printer is not plugged in" instead of a wall of red.
    """


# Lines Buddy sends on its own, never as an answer to anything we asked.
# These are always dropped.
_NOISE = ("echo:", "//", "start", "wait", "adc")

# Automatic temperature reports.  Dropped too, unless we are collecting a
# reply, because M105's answer looks exactly like one.
_TEMPERATURE = ("t:", "b:", "a:")


def _is_chatter(line, collecting=False):
    """True if this line is unsolicited noise rather than a reply.

    Be careful what goes in here.  M115 answers with FIRMWARE_NAME: and Cap:
    lines and M114 answers with X: ... - filtering those by accident makes the
    firmware look silent when it is in fact talking.
    """
    low = line.lower()
    if any(low.startswith(tag) for tag in _NOISE):
        return True
    if not collecting and any(low.startswith(tag) for tag in _TEMPERATURE):
        return True
    return False


def config_path():
    """The calibration file lives next to plotter.py, not next to the script."""
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), CONFIG_NAME)


def load_config(path=None):
    """Read the calibration file.  Missing is fine; broken is worth saying.

    Students never edit this.  The teacher's calibration tool writes it, and
    Plotter reads it automatically, so student programs stay free of numbers
    that depend on this particular machine.
    """
    path = path or config_path()
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return {}
    except ValueError:
        print("Warning: %s is not valid JSON, so I am ignoring it." % path)
        print("Ask your teacher to run the calibration tool again.")
        return {}
    except OSError as e:
        print("Warning: could not read %s (%s); using defaults." % (path, e))
        return {}
    if not isinstance(data, dict):
        print("Warning: %s should contain a JSON object; ignoring it." % path)
        return {}
    if isinstance(data.get("pen_offset"), list):
        data["pen_offset"] = tuple(data["pen_offset"])
    return data


def save_config(values, path=None):
    """Write the calibration file.  Used by the teacher's calibration tool."""
    path = path or config_path()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(values, f, indent=2, sort_keys=True)
        f.write("\n")
    return path


def _friendly_open_error(port, err):
    """Turn a pyserial exception into something a student can act on."""
    text = str(err).lower()
    if "permission" in text or "access is denied" in text or "busy" in text:
        return ("The printer's port (%s) is already in use.\n"
                "Usually that means someone else is connected to the printer,\n"
                "or a program like PrusaSlicer or another Thonny window still\n"
                "has it open.  Only one person can use the printer at a time.\n"
                "Ask whoever is connected to run finish() or close their\n"
                "program, then try again." % port)
    if "could not open" in text or "filenotfound" in text or "no such" in text:
        return ("I found the port %s but it disappeared when I tried to open\n"
                "it.  Unplug the USB cable, plug it back in, wait a few\n"
                "seconds, and run your program again." % port)
    return ("I couldn't open the printer's port (%s).\n"
            "Unplug the USB cable, plug it back in, and try again.\n"
            "Technical detail: %s" % (port, err))



# --------------------------------------------------------------------------
# Serial helpers
# --------------------------------------------------------------------------

def find_ports():
    """Return a list of (device, description) for all serial ports."""
    if list_ports is None:
        return []
    return [(p.device, p.description, p.vid) for p in list_ports.comports()]


# Ports that are definitely not a printer.  Windows in particular lists every
# paired Bluetooth device as a COM port, and connecting to one of those just
# hangs, so never guess them.
_NOT_A_PRINTER = ("bluetooth", "bthmodem", "wireless", "debug-console")


def _looks_like_bluetooth(dev, desc):
    text = ("%s %s" % (dev, desc)).lower()
    return any(tag in text for tag in _NOT_A_PRINTER)


def find_prusa_port():
    """Best guess at the printer's port.

    The Prusa USB vendor id is the only reliable answer.  Failing that we
    accept a USB CDC port (usbmodem on macOS, ttyACM on Linux) and, on
    Windows, a COM port that is not a Bluetooth link.  A wrong guess here
    would mean talking to somebody's headset, so guess conservatively.
    """
    ports = find_ports()
    for dev, desc, vid in ports:
        if vid == PRUSA_VID:
            return dev
    for dev, desc, vid in ports:
        d = dev.lower()
        if _looks_like_bluetooth(dev, desc):
            continue
        if "usbmodem" in d or "ttyacm" in d:
            return dev
        # On Windows a real USB device has a vendor id; Bluetooth links
        # generally do not.  Require one before guessing a bare COM port.
        if d.startswith("com") and vid is not None:
            return dev
    return None


# --------------------------------------------------------------------------
# The Plotter turtle
# --------------------------------------------------------------------------

class Plotter(turtle.Turtle):

    # Fallbacks, used only when the calibration file has nothing to say.
    DEFAULTS = {
        "paper_mm": 150.0,        # size of the square drawing area
        "scale": 0.25,            # mm per turtle unit
        "bed_mm": 180.0,          # Prusa MINI bed size
        "pen_up_z": 5.0,          # mm - the calibration tool overwrites these
        "pen_down_z": 1.0,        # mm
        "pen_offset": (0.0, 0.0),  # (dx, dy) mm from nozzle to pen tip
        "draw_feed": 1500,        # mm/min while drawing
        "travel_feed": 4000,      # mm/min while the pen is up
    }

    def __init__(self,
                 live=False,
                 port=None,
                 paper_mm=None,
                 scale=None,
                 bed_mm=None,
                 pen_up_z=None,
                 pen_down_z=None,
                 pen_offset=None,
                 draw_feed=None,
                 travel_feed=None,
                 lockstep=True,       # wait for each move to finish
                 show_paper=True,
                 config=None):
        super().__init__()

        # Settings come from three places, in order of who wins:
        #   1. what the student passed in (rare, and always deliberate)
        #   2. plotter_config.json, written by the teacher's calibration tool
        #   3. DEFAULTS above
        self.config = load_config() if config is None else dict(config)
        given = {
            "paper_mm": paper_mm, "scale": scale, "bed_mm": bed_mm,
            "pen_up_z": pen_up_z, "pen_down_z": pen_down_z,
            "pen_offset": pen_offset, "draw_feed": draw_feed,
            "travel_feed": travel_feed,
        }
        for name, value in given.items():
            if value is None:
                value = self.config.get(name, self.DEFAULTS[name])
            setattr(self, name, value)
        if isinstance(self.pen_offset, list):
            self.pen_offset = tuple(self.pen_offset)

        self.lockstep = lockstep

        self.strokes = []        # list of strokes; each is a list of (x, y) mm
        self._current = None     # stroke being drawn right now
        self._warned = False
        self.ser = None
        self._hw_down = False
        self._homed = False
        self.firmware = None
        self.grbl = None             # GrblBackend when driving the AX4
        self.backend_name = self.config.get("backend", "mini")

        if show_paper:
            self._draw_paper_outline()

        self.speed(6)

        if live:
            try:
                self.connect(port)
                self.prepare()
            except PlotterError as e:
                print()
                print(e)
                print()
                print("Carrying on with the screen only - your drawing will")
                print("still appear in the turtle window and still save.")

    # ---- screen extras --------------------------------------------------

    def _draw_paper_outline(self):
        half = (self.paper_mm / 2) / self.scale
        guide = turtle.Turtle()
        guide.hideturtle()
        guide.speed(0)
        guide.pencolor("lightgray")
        guide.penup()
        guide.goto(-half, -half)
        guide.pendown()
        for _ in range(4):
            guide.forward(2 * half)
            guide.left(90)
        guide.penup()

    # ---- coordinate conversion ------------------------------------------

    def _to_mm(self, x, y):
        """Turtle units -> pen position in mm on the bed (centre = 90, 90)."""
        return (self.bed_mm / 2 + x * self.scale,
                self.bed_mm / 2 + y * self.scale)

    def _clamped(self, mx, my):
        """Keep the pen inside the paper square."""
        lo = self.bed_mm / 2 - self.paper_mm / 2
        hi = self.bed_mm / 2 + self.paper_mm / 2
        cx = min(max(mx, lo), hi)
        cy = min(max(my, lo), hi)
        if (cx, cy) != (mx, my) and not self._warned:
            print("Warning: a move went outside the paper and was clamped.")
            self._warned = True
        return cx, cy

    def _nozzle(self, mx, my):
        """Pen position -> nozzle position, checked against the bed limits."""
        nx = mx - self.pen_offset[0]
        ny = my - self.pen_offset[1]
        nx = min(max(nx, 0.0), self.bed_mm)
        ny = min(max(ny, 0.0), self.bed_mm)
        return nx, ny

    # ---- movement hooks (this is where turtle meets the pen) ------------

    def _goto(self, end):
        start = self.pos()
        down = self.isdown()

        mx, my = self._clamped(*self._to_mm(end[0], end[1]))

        if down:
            if self._current is None:
                # A new stroke starts here.  Keep a reference to the same
                # list in self.strokes so later points land in it too.
                sx, sy = self._clamped(*self._to_mm(start[0], start[1]))
                self._current = [(sx, sy)]
                self.strokes.append(self._current)
            self._current.append((mx, my))
        else:
            self._current = None

        # hardware first, then screen, so the pen never runs ahead of code
        grbl = getattr(self, "grbl", None)
        if grbl is not None:
            # AX4: paper coordinates, origin at the paper centre, no clamp
            grbl.pen(down)
            grbl.move(end[0] * self.scale, end[1] * self.scale,
                      self.draw_feed if down else self.travel_feed)
            if self.lockstep:
                grbl.wait()
        elif self.ser is not None:
            self._hw_pen(down)
            nx, ny = self._nozzle(mx, my)
            feed = self.draw_feed if down else self.travel_feed
            self._send("G1 X%.3f Y%.3f F%d" % (nx, ny, feed))
            if self.lockstep:
                self._send("M400")

        super()._goto(end)

    def penup(self):
        super().penup()
        self._current = None
        if getattr(self, "grbl", None) is not None:
            self.grbl.pen(False)
        elif self.ser is not None:
            self._hw_pen(False)

    def pendown(self):
        super().pendown()
        if getattr(self, "grbl", None) is not None:
            self.grbl.pen(True)
        elif self.ser is not None:
            self._hw_pen(True)

    # turtle defines these aliases at class-creation time, so re-bind them
    pu = up = penup
    pd = down = pendown

    # ---- serial / printer ------------------------------------------------

    def connect(self, port=None, baud=115200):
        """Open the serial port and say hello.  Moves nothing.

        Homing and the first travel move live in prepare(), so that simply
        connecting can never drive the pen into the bed.
        """
        if getattr(self, "backend_name", "mini") == "grbl":
            from grbl_backend import GrblBackend
            print("Connecting to the AX4 plotter ...")
            self.grbl = GrblBackend(self.config)
            self.firmware = self.grbl.connect(port)
            print("Connected.  Nothing has moved yet.")
            return self.firmware

        if serial is None:
            raise PlotterError(
                "pyserial is not installed, so I can't talk to the printer.\n"
                "In Thonny: Tools > Manage packages, search for 'pyserial',\n"
                "click Install, then restart Thonny.\n"
                "(You can still draw on screen and save SVG and G-code.)")

        port = port or find_prusa_port()
        if port is None:
            raise PlotterError(
                "I can't find the printer.\n"
                "  1. Is the printer turned on?\n"
                "  2. Is the USB cable plugged into the small socket on the\n"
                "     printer's control board (not the USB stick socket)?\n"
                "  3. Some USB cables only carry power and no data.  If you\n"
                "     are not sure, try a different cable.\n"
                "To see what your computer can find, run:\n"
                "    python plotter.py --ports")

        print("Connecting to", port, "...")
        try:
            self.ser = serial.Serial(port, baud, timeout=SERIAL_TIMEOUT)
        except Exception as e:
            self.ser = None
            raise PlotterError(_friendly_open_error(port, e))

        time.sleep(2.0)                  # the board reboots when the port opens
        self.ser.reset_input_buffer()

        info = self._send("M115", collect=True)   # firmware handshake
        self.firmware = " | ".join(info) if info else "(no reply to M115)"

        self._send("M155 S0")            # stop automatic temperature reports
        self._send("M104 S0")            # nozzle heater off
        self._send("M140 S0")            # bed heater off
        self._send("M107")               # part fan off
        self._send("G21")                # millimetres
        self._send("G90")                # absolute positioning
        self._homed = False
        print("Connected.  Nothing has moved yet.")
        return self.firmware

    def prepare(self):
        """Home the printer and lift the pen.  THIS MOVES THE PRINTER.

        Z-homing can push a fitted pen into the bed, so this is deliberately
        separate from connect() and must be called on purpose.
        """
        if getattr(self, "grbl", None) is not None:
            # The AX4 has no homing: wherever the pen is now is the centre.
            self.grbl.pen(False)
            self.grbl.set_origin()
            print("Ready.  The pen's current position is the centre of "
                  "the paper.")
            return

        if self.ser is None:
            raise PlotterError("Not connected.  Call connect() first.")
        print("Homing (this takes a moment)...")
        self._send("G28", timeout=180)
        self._send("G1 Z%.3f F600" % self.pen_up_z)
        self._hw_down = False
        nx, ny = self._nozzle(self.bed_mm / 2, self.bed_mm / 2)
        self._send("G1 X%.3f Y%.3f F%d" % (nx, ny, self.travel_feed))
        self._send("M400")
        self._homed = True
        print("Ready.  Pen is up at the centre of the paper.")

    def _hw_pen(self, down):
        if down == self._hw_down:
            return
        z = self.pen_down_z if down else self.pen_up_z
        self._send("G1 Z%.3f F600" % z)
        self._send("M400")
        self._hw_down = down

    def _send(self, line, timeout=SERIAL_TIMEOUT_LONG, collect=False):
        """Send one G-code line and wait for the printer's 'ok'.

        Buddy firmware talks a lot: a boot banner, "echo:" lines, "busy:
        processing" while it is working, temperature reports, and "//" action
        comments.  Only "ok" means the command finished.  Anything that is not
        "ok" and not an error is chatter; collect=True returns it, which is how
        M115 gives us the firmware string.

        A "busy:" line means the printer is alive and working, so it pushes the
        deadline back rather than counting towards the timeout.
        """
        if self.ser is None:
            raise PlotterError("Not connected to the printer.")

        self.ser.write((line + "\n").encode("ascii"))
        self.ser.flush()

        collected = []
        deadline = time.time() + timeout
        while time.time() < deadline:
            raw = self.ser.readline()
            if not raw:
                continue
            resp = raw.decode("ascii", errors="replace").strip()
            if not resp:
                continue

            low = resp.lower()

            if low.startswith("ok"):
                # Buddy sometimes answers "ok T:24.1 /0.0" - trailing data,
                # but the command is finished either way.
                extra = resp[2:].strip()
                if collect and extra:
                    collected.append(extra)
                return collected

            if low.startswith("error") or resp.startswith("!!"):
                raise PlotterError("The printer reported a problem:\n  " + resp
                                   + "\nafter the command: " + line)

            if low.startswith("busy"):
                # still working, so this is not a stall: give it more time
                deadline = time.time() + timeout
                continue

            if _is_chatter(resp, collecting=collect):
                continue

            if collect:
                collected.append(resp)

        raise PlotterError(
            "The printer stopped replying after I sent: " + line + "\n"
            "Try turning the printer off and on again, unplugging and\n"
            "replugging the USB cable, then running your program again.")

    def finish(self):
        """Lift the pen, park the head, release motors, close the port."""
        if getattr(self, "grbl", None) is not None:
            try:
                self.grbl.finish(self.travel_feed)
            finally:
                self.grbl = None
            print("Done.  Pen up, head back at the centre.")
            return

        if self.ser is None:
            return
        try:
            self._hw_pen(False)
            self._send("G1 X0 Y%.1f F%d" % (self.bed_mm - 10, self.travel_feed))
            self._send("M400")
            self._send("M84")
        finally:
            self.ser.close()
            self.ser = None
        print("Done. Pen parked and motors released.")

    # ---- exports --------------------------------------------------------

    def save_svg(self, path):
        """Write the strokes as an SVG in mm, one <path> per stroke, in order."""
        size = self.paper_mm
        lo = self.bed_mm / 2 - self.paper_mm / 2
        lines = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<svg xmlns="http://www.w3.org/2000/svg" '
            'width="%gmm" height="%gmm" viewBox="0 0 %g %g">' % (size, size, size, size),
            '  <!-- generated by plotter.py; paths are in drawing order -->',
        ]
        for i, stroke in enumerate(self.strokes):
            if len(stroke) < 2:
                continue
            pts = []
            for (mx, my) in stroke:
                # SVG y grows downward; paper y grows upward
                pts.append("%.3f,%.3f" % (mx - lo, size - (my - lo)))
            lines.append('  <path id="stroke%d" d="M %s" fill="none" '
                         'stroke="black" stroke-width="0.4" '
                         'stroke-linecap="round" stroke-linejoin="round"/>'
                         % (i, " L ".join(pts)))
        lines.append("</svg>")
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        print("Saved", path, "with", len(self.strokes), "strokes")

    def save_gcode(self, path):
        """Write a standalone G-code file for the printer's USB stick."""
        g = [
            "; generated by plotter.py (pen plotter on Prusa MINI)",
            "; pen up Z=%.2f  pen down Z=%.2f  offset=(%.2f, %.2f)"
            % (self.pen_up_z, self.pen_down_z, *self.pen_offset),
            "M104 S0 ; nozzle heater off",
            "M140 S0 ; bed heater off",
            "M107    ; fan off",
            "G21     ; mm",
            "G90     ; absolute",
            "G28     ; home",
            "G1 Z%.3f F600" % self.pen_up_z,
        ]
        for stroke in self.strokes:
            if len(stroke) < 2:
                continue
            nx, ny = self._nozzle(*stroke[0])
            g.append("G1 X%.3f Y%.3f F%d" % (nx, ny, self.travel_feed))
            g.append("G1 Z%.3f F600" % self.pen_down_z)
            for (mx, my) in stroke[1:]:
                nx, ny = self._nozzle(mx, my)
                g.append("G1 X%.3f Y%.3f F%d" % (nx, ny, self.draw_feed))
            g.append("G1 Z%.3f F600" % self.pen_up_z)
        g += [
            "G1 X0 Y%.1f F%d ; park" % (self.bed_mm - 10, self.travel_feed),
            "M84 ; motors off",
        ]
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(g) + "\n")
        print("Saved", path)


# --------------------------------------------------------------------------
# Command-line helpers for the teacher
# --------------------------------------------------------------------------

def _cli():
    if "--ports" in sys.argv:
        ports = find_ports()
        if not ports:
            print("No serial ports found (or pyserial not installed).")
        for dev, desc, vid in ports:
            tag = "  <-- Prusa" if vid == PRUSA_VID else ""
            print("%-28s %s%s" % (dev, desc, tag))
        return

    if "--jog" in sys.argv:
        # Connect, home, then let you move Z by typing numbers.
        p = Plotter(live=False, show_paper=False)
        turtle.Screen().tracer(0)
        p.connect()
        print("Type a Z height in mm (e.g. 2.5) and press Enter to move there.")
        print("Type 'x 90 y 90' style moves too. Type q to quit.")
        while True:
            s = input("z> ").strip().lower()
            if s in ("q", "quit", "exit"):
                break
            try:
                if s.startswith("x") or s.startswith("y"):
                    parts = s.replace("x", " x ").replace("y", " y ").split()
                    cmd = "G1"
                    for i in range(0, len(parts), 2):
                        cmd += " %s%.3f" % (parts[i].upper(), float(parts[i + 1]))
                    p._send(cmd + " F1500")
                else:
                    p._send("G1 Z%.3f F300" % float(s))
                p._send("M400")
            except Exception as e:
                print("?", e)
        p.finish()
        return

    print(__doc__)


if __name__ == "__main__":
    _cli()
