"""
grbl_backend.py  -  talks to a GRBL pen plotter (the IKRANBIRD AX4).

Coordinates are millimetres from the origin, which sits margin_mm in from
the top-left (or bottom-left) corner of the sheet; +X is right, +Y is up
the sheet.  The AX4 has no homing switches, so 0,0 is wherever the head was
when set_origin() ran.  Moves off the drawable area are refused, never
clamped.

Facts this relies on (measured 2026-10-04, see docs/HARDWARE_NOTES.md):
  * opening the port resets the board; "Grbl 0.9i ..." follows ~1.5 s later
  * G1 is acknowledged when queued; "G4 P0" answers only when motion stops
  * pen up = M5 (also the state after any reset), pen down = M3 S<n>
"""

import math
import re
import time

from plotter import PlotterError

try:
    import serial
    from serial.tools import list_ports
except ImportError:          # pyserial missing: connect() explains
    serial = None
    list_ports = None

CH340_VID = 0x1A86           # the AX4's USB-serial chip
BAUD = 115200
LETTER_MM = (279.4, 215.9)   # US Letter, landscape
CMD_TIMEOUT = 30             # s for one command (a long move then G4 P0)
BANNER_TIMEOUT = 5

LOST = ("Connection lost.  Lift the pen by hand if it is down, reconnect,\n"
        "and set the origin again.")


class PlotStopped(PlotterError):
    """Raised inside a running plot when STOP was pressed."""


ORIGINS = ("top_left", "bottom_left")


def drawable_area(origin="top_left", paper=LETTER_MM, margin=10.0):
    """(xmin, xmax, ymin, ymax) in mm from the origin.  The pen is set
    margin mm in from that corner, so the area is the sheet less a margin
    on every side.  Top-left: drawings go right and down (y negative)."""
    w, h = paper[0] - 2 * margin, paper[1] - 2 * margin
    if origin == "top_left":
        return (0.0, w, -h, 0.0)
    if origin == "bottom_left":
        return (0.0, w, 0.0, h)
    raise ValueError("origin must be one of %s" % (ORIGINS,))


def find_grbl_port():
    if list_ports is None:
        return None
    for p in list_ports.comports():
        if p.vid == CH340_VID:
            return p.device
    return None


def _open_error(port, err):
    text = str(err).lower()
    if "permission" in text or "access is denied" in text or "busy" in text:
        return ("The plotter's port (%s) is in use by another program -\n"
                "probably Candle.  Click Disconnect in Candle (or close it)\n"
                "and try again." % port)
    return ("I couldn't open the plotter's port (%s).\n"
            "Unplug the USB cable, plug it back in, and try again.\n"
            "Technical detail: %s" % (port, err))


def _default_opener(port):
    return serial.Serial(port, BAUD, timeout=0.2)


class GrblBackend:

    def __init__(self, config=None, opener=None):
        config = config or {}
        self.pen_down_s = int(config.get("pen_down_s", 80))
        self.pen_touch_s = int(config.get("pen_touch_s", 60))
        self.servo_wait = float(config.get("servo_wait_s", 0.3))
        self.limits = drawable_area(config.get("origin", "top_left"),
                                    margin=float(config.get("margin_mm", 10.0)))
        self._opener = opener
        self.ser = None
        self.firmware = None
        self.is_down = False
        self.origin_set = False
        self.paused = False
        self._stopping = False
        self.work_pos = None         # (x, y) from the origin, last "?" seen

    # ---- connection -----------------------------------------------------

    @property
    def connected(self):
        return self.ser is not None

    def connect(self, port=None, banner_timeout=BANNER_TIMEOUT):
        """Open the port and wait for GRBL to say hello.  Moves nothing."""
        opener = self._opener
        if opener is None:
            if serial is None:
                raise PlotterError(
                    "pyserial is not installed.  In Thonny: Tools > Manage\n"
                    "packages, search for 'pyserial', Install, restart Thonny.")
            opener = _default_opener
        port = port or find_grbl_port()
        if port is None:
            raise PlotterError("Can't find the plotter.  Is it plugged in "
                               "and switched on?")
        if self.ser is not None:
            self.close()
        try:
            self.ser = opener(port)
        except Exception as e:
            self.ser = None
            raise PlotterError(_open_error(port, e))
        self.is_down = False         # the reset leaves the servo at M5
        self.origin_set = False
        self.paused = False
        self._stopping = False
        self.firmware = self._wait_banner(banner_timeout)
        if self.firmware is None:
            self.close()
            raise PlotterError("The plotter didn't answer.  Unplug and "
                               "replug the USB cable, then try again.")
        self._cmd("G21")
        self._cmd("G90")
        return self.firmware

    def close(self):
        ser, self.ser = self.ser, None
        self.origin_set = False
        if ser is not None:
            try:
                ser.close()
            except Exception:
                pass

    def _wait_banner(self, timeout):
        deadline = time.time() + timeout
        while time.time() < deadline:
            line = self._readline()
            if line.startswith("Grbl"):
                return line
        return None

    def _readline(self):
        if self.ser is None:
            raise PlotterError(LOST)
        try:
            raw = self.ser.readline()
        except Exception as e:
            self.close()
            raise PlotterError("%s\n(%s)" % (LOST, e))
        return raw.decode("ascii", "replace").strip()

    def _write(self, data):
        if self.ser is None:
            raise PlotterError("Not connected to the plotter.")
        try:
            self.ser.write(data)
        except Exception as e:
            self.close()
            raise PlotterError("%s\n(%s)" % (LOST, e))

    def _cmd(self, line, timeout=CMD_TIMEOUT):
        """Send one line and wait for "ok".  Returns the other lines seen."""
        # GRBL ignores "!" while idle (between strokes, during a servo
        # dwell), so Pause also holds the next command here on the computer.
        while self.paused and not self._stopping:
            time.sleep(0.05)
        if self._stopping:
            raise PlotStopped("Stopped.")
        self._write((line + "\n").encode("ascii"))
        got = []
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self._stopping:
                raise PlotStopped("Stopped.")
            if self.paused:          # a paused plot is not a dead plotter
                deadline = time.time() + timeout
            resp = self._readline()
            if not resp:
                continue
            if resp == "ok":
                return got
            if resp.startswith("error"):
                raise PlotterError("The plotter rejected '%s': %s"
                                   % (line, resp))
            if resp.startswith("ALARM"):
                self.origin_set = False
                raise PlotterError("The plotter raised an alarm after '%s': "
                                   "%s\nSet the origin again." % (line, resp))
            got.append(resp)
        raise PlotterError("The plotter stopped replying after '%s'.\n"
                           "Unplug and replug the USB cable." % line)

    # ---- pen ------------------------------------------------------------

    def servo(self, s):
        """Move the pen servo: s=None lifts (M5), otherwise M3 S<s>.

        Waits for motion to finish first, so the pen never drops while the
        head is still travelling, and dwells while the servo moves.
        """
        self._cmd("G4 P0")
        self._cmd("M5" if s is None else "M3 S%d" % s)
        self._cmd("G4 P%.2f" % self.servo_wait)
        self.is_down = s is not None

    def pen(self, down):
        if down == self.is_down:
            return
        self.servo(self.pen_down_s if down else None)

    # ---- motion ---------------------------------------------------------

    def move(self, x, y, feed):
        x0, x1, y0, y1 = self.limits
        if not (x0 - 1e-6 <= x <= x1 + 1e-6 and y0 - 1e-6 <= y <= y1 + 1e-6):
            raise PlotterError(
                "A move to (%.1f, %.1f) mm is off the paper (x must be %.1f "
                "to %.1f, y %.1f to %.1f mm)." % (x, y, x0, x1, y0, y1))
        self._cmd("G1 X%.3f Y%.3f F%d" % (x, y, feed))

    def wait(self):
        self._cmd("G4 P0")

    def set_origin(self):
        """The head's current position becomes 0,0 (the origin corner)."""
        self._cmd("G4 P0")
        self._cmd("G92 X0 Y0")
        self.origin_set = True

    def jog(self, dx, dy, feed=1500):
        """Relative move with the pen up.  Not bounds-checked: used to find
        the origin corner of the sheet before the origin exists."""
        self.pen(False)
        self._cmd("G91")
        try:
            self._cmd("G1 X%.3f Y%.3f F%d" % (dx, dy, feed))
        finally:
            self._cmd("G90")
        self.wait()

    def position(self):
        """(x, y) machine position in mm, from GRBL's "?" status report."""
        self._write(b"?")
        deadline = time.time() + 2
        while time.time() < deadline:
            line = self._readline()
            m = re.search(r"MPos:(-?[\d.]+),(-?[\d.]+)", line)
            if m:
                w = re.search(r"WPos:(-?[\d.]+),(-?[\d.]+)", line)
                if w:
                    self.work_pos = (float(w.group(1)), float(w.group(2)))
                return float(m.group(1)), float(m.group(2))
        raise PlotterError("The plotter didn't report its position.")

    def work_position(self):
        """(x, y) in mm from the origin (GRBL's WPos), or None if unknown."""
        self.position()
        return self.work_pos

    def jog_hold(self, dx, dy, keep_going, step=3.0, feed=900, max_mm=100.0):
        """Move in direction (dx, dy) for as long as keep_going() is True.

        GRBL 0.9 has no jog command, so this queues short relative moves,
        sending the next one when the head is half a step from the end of
        the last.  At most about 1.5 steps are ever queued, so the head
        stops within ~5 mm of letting go.  No limit switches on the AX4:
        each hold is capped at max_mm.
        """
        self.pen(False)
        self._cmd("G91")
        try:
            start = self.position()
            sent = 0.0
            while keep_going() and sent + step <= max_mm + 1e-9:
                self._cmd("G1 X%.3f Y%.3f F%d" % (dx * step, dy * step, feed))
                sent += step
                while keep_going():
                    x, y = self.position()
                    if sent - math.hypot(x - start[0], y - start[1]) <= step / 2:
                        break
                    time.sleep(0.02)
        finally:
            self._cmd("G90")
        self.wait()

    # ---- realtime -------------------------------------------------------

    def pause(self):
        self._write(b"!")
        self.paused = True

    def resume(self):
        self._write(b"~")
        self.paused = False

    def stop(self):
        """Feed hold, then soft reset.  Safe to call from any thread.

        A plot running in another thread sees PlotStopped on its next read
        and should call recover(); when idle, call recover() yourself.
        """
        self._stopping = True
        self.paused = False
        self._write(b"!")
        time.sleep(0.2)
        self._write(b"\x18")
        self.is_down = False         # reset puts the servo back at M5
        self.origin_set = False

    def recover(self):
        """After stop(): wait for the reset banner, unlock, mm + absolute.

        Retries if STOP is pressed again while this runs (a double click).
        """
        for _ in range(3):
            self._wait_banner(2.0)
            self._stopping = False
            try:
                self._cmd("$X")
                self._cmd("G21")
                self._cmd("G90")
                return
            except PlotStopped:
                continue
        raise PlotterError("The plotter didn't recover after STOP.  Click "
                           "Disconnect, then Connect.")

    # ---- settings -------------------------------------------------------

    def read_settings(self):
        out = {}
        for line in self._cmd("$$"):
            if line.startswith("$") and "=" in line:
                key, rest = line[1:].split("=", 1)
                try:
                    out[int(key)] = float(rest.split()[0])
                except ValueError:
                    pass
        return out

    def write_setting(self, num, value):
        self._cmd("$%d=%.3f" % (num, value))

    def finish(self, travel_feed=3000):
        """Pen up, back to the origin if there is one, close the port."""
        if self.ser is None:
            return
        try:
            self.pen(False)
            if self.origin_set:
                self.move(0.0, 0.0, travel_feed)
                self.wait()
        finally:
            self.close()
