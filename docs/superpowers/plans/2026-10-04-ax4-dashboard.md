# AX4 Dashboard and Turtle Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Plot students' plain `import turtle` programs on the IKRANBIRD AX4 from a teacher's Tkinter dashboard with guided pen setup, origin, calibration, and a real STOP.

**Architecture:** A new `grbl_backend.py` talks to the AX4 (GRBL 0.9i). `run_turtle.py` runs a student file in a subprocess with `turtle.Turtle` swapped for a recording turtle and prints strokes as JSON. `dashboard_logic.py` holds every decision (scale, fit, checklist, time, calibration maths, plotting loop) with no Tkinter, and `dashboard.py` + `dashboard_wizards.py` are thin Tkinter windows on top. `plotter.py` gains an AX4 path for live Thonny use.

**Tech Stack:** Python 3.10 (Thonny's bundled interpreter), stdlib (`tkinter`, `turtle`, `subprocess`, `json`, `threading`, `unittest`) + `pyserial`.

**Spec:** `docs/superpowers/specs/2026-10-04-ax4-dashboard-design.md`

**Deviation from the spec (agreed reason):** the spec says the Prusa code is "moved out" into a `MiniBackend`. The existing 45 tests call `Plotter._send`, `Plotter.ser`, `_hw_pen` directly and build bare `Plotter` objects with `__new__`. Moving the code would force rewriting those tests. This plan leaves the Prusa code in `Plotter` exactly as it is (it *is* the MINI backend) and adds the AX4 path beside it, selected by `"backend"` in the config. Behaviour matches the spec; the 45 tests stay untouched.

**Not a git repository:** the teacher commits by hand. Where the skill would say "commit", each task ends with a **Checkpoint** that runs the whole suite instead.

## Global Constraints

- Dependencies: stdlib + `pyserial` only. Must run under Thonny's bundled Python 3.10.11 on Windows (and stay Mac-compatible: no Windows-only imports at module level).
- AX4 serial: CH340 VID `0x1A86`, 115200 baud, banner starts with `Grbl`, wait up to 5 s for it after opening.
- Pen: up `M5`; touch `M3 S60`; down `M3 S80`; servo wait `G4 P0.30` after every pen change; `G4 P0` before every pen change.
- Lockstep: `G4 P0` is the "wait until motion finished" command. `G1` `ok` means queued only.
- Paper: US Letter landscape 279.4 x 215.9 mm, 10 mm margin, usable X +/-129.7 mm, Y +/-97.95 mm, origin at paper centre.
- Scale: 100% = 0.25 mm per turtle step.
- Off-paper moves are refused (raise), never clamped, on the AX4 path.
- Student program time limit: 20 s.
- Nothing moves except in response to an explicit teacher action (a button click, or `Plotter(live=True)` in a script the teacher runs).
- Hardware stages in Task 7 require the teacher present and an explicit "go" for each stage.
- The 45 existing tests (`tests/test_exports.py`, `tests/test_serial_protocol.py`, `tests/test_config.py`) must keep passing unchanged.
- Full suite command (Git Bash, project root): `for f in tests/test_*.py; do python "$f" || break; done`

## Review Focus

1. A student file written as `from turtle import *` with module-level `forward()` calls must record its lines (pinned in Task 3: `test_module_level_functions_record`).
2. A student file that `print()`s (including braces/quotes) must not corrupt the runner's JSON (Task 3: `test_student_print_does_not_corrupt_json`).
3. A program that draws nothing must not crash fit/estimate and must block Plot with "Nothing to plot" (Task 4: `test_empty_drawing`).
4. A Pause longer than the 30 s command timeout must not be reported as "stopped replying" (Task 1: `test_pause_extends_the_deadline`).
5. STOP pressed while nothing is plotting must recover (banner, `$X`) without hanging, and must clear the origin (Task 1: `test_stop_while_idle_recovers`).

---

## File structure

| File | Responsibility |
|---|---|
| `grbl_backend.py` (create) | AX4 serial protocol: connect, pen/servo, move with bounds, wait, origin, jog, pause/resume/stop/recover, settings. Paper constants. |
| `tests/fake_grbl.py` (create) | Fake serial port behaving like GRBL 0.9i. Shared by tests. |
| `tests/test_grbl_backend.py` (create) | Backend tests. |
| `plotter.py` (modify) | AX4 path in `connect`, `prepare`, `_goto`, `penup`, `pendown`, `finish`. |
| `tests/test_plotter_grbl.py` (create) | Plotter-on-AX4 tests. |
| `plotter_config.json` (modify) | Add AX4 keys, `"backend": "grbl"`. |
| `run_turtle.py` (create) | Run a student file, record strokes, print JSON. |
| `tests/samples/*.py` (create) | Sample student programs. |
| `tests/test_run_turtle.py` (create) | Runner tests. |
| `dashboard_logic.py` (create) | Scale, fit, bounds, time, checklist, calibration maths, test strokes, plot loop, SVG, run_student. |
| `tests/test_dashboard_logic.py` (create) | Logic tests. |
| `dashboard.py` (create) | Main Tkinter window. |
| `dashboard_wizards.py` (create) | Pen setup and calibration wizards. |
| `tests/test_dashboard_smoke.py` (create) | Builds the window and wizards against the fake port. |
| `docs/SETUP.md`, `docs/HARDWARE_NOTES.md`, `SESSION_NOTES.md` (modify) | Teacher instructions, findings, status. |

---

### Task 1: GRBL backend

**Files:**
- Create: `grbl_backend.py`
- Create: `tests/fake_grbl.py`
- Test: `tests/test_grbl_backend.py`

**Interfaces:**
- Consumes: `plotter.PlotterError`.
- Produces:
  - constants `LETTER_MM = (279.4, 215.9)`, `CH340_VID`, `BAUD`
  - `usable_half(paper=LETTER_MM, margin=10.0) -> (float, float)`
  - `find_grbl_port() -> str | None`
  - `class PlotStopped(PlotterError)`
  - `class GrblBackend(config: dict | None = None, opener=None)` with attributes `pen_down_s:int`, `pen_touch_s:int`, `servo_wait:float`, `limits:(float,float)`, `firmware:str|None`, `is_down:bool`, `origin_set:bool`, `paused:bool`, property `connected:bool`, and methods `connect(port=None, banner_timeout=5) -> str`, `close()`, `servo(s: int|None)`, `pen(down: bool)`, `move(x, y, feed)`, `wait()`, `set_origin()`, `jog(dx, dy, feed=1500)`, `pause()`, `resume()`, `stop()`, `recover()`, `read_settings() -> dict[int, float]`, `write_setting(num: int, value: float)`, `finish(travel_feed=3000)`, and internal `_cmd(line, timeout=30) -> list[str]`.
  - `tests/fake_grbl.py`: `BANNER`, `class FakeGrbl(replies=None, banner=True, read_delay=0.0)` with `.sent` (list of text lines), `.raw` (list of bytes writes), `.fail_reads`, `.closed`.

- [ ] **Step 1: Write the fake port**

Create `tests/fake_grbl.py`:

```python
"""
fake_grbl.py  -  a stand-in for the AX4's serial port, for offline tests.

Behaves like GRBL 0.9i as measured on 2026-10-04:
  * a banner when "opened" and again after a Ctrl-X soft reset
  * "ok" for every line, unless `replies` says otherwise
  * realtime bytes (!, ~, ?) get no "ok"
"""

import time

BANNER = "Grbl 0.9i ['$' for help]"


class FakeGrbl:

    def __init__(self, replies=None, banner=True, read_delay=0.0):
        self.replies = dict(replies or {})  # command prefix -> reply lines
        self.sent = []          # text lines received, newline stripped
        self.raw = []           # every write, as bytes
        self.read_delay = read_delay
        self.fail_reads = False
        self.closed = False
        self._pending = ["", BANNER] if banner else []

    def write(self, data):
        self.raw.append(bytes(data))
        if data in (b"!", b"~"):
            return len(data)
        if data == b"?":
            self._pending.append(
                "<Idle,MPos:0.000,0.000,0.000,WPos:0.000,0.000,0.000>")
            return 1
        if data == b"\x18":
            self._pending += ["", BANNER]
            return 1
        line = data.decode("ascii").strip()
        self.sent.append(line)
        for prefix, lines in self.replies.items():
            if line.startswith(prefix):
                self._pending += list(lines)
                break
        else:
            self._pending.append("ok")
        return len(data)

    def readline(self):
        if self.fail_reads:
            raise OSError("device disconnected")
        if self.read_delay:
            time.sleep(self.read_delay)
        if not self._pending:
            return b""              # looks like a read timeout
        return (self._pending.pop(0) + "\r\n").encode("ascii")

    def close(self):
        self.closed = True
```

- [ ] **Step 2: Write the failing tests**

Create `tests/test_grbl_backend.py`:

```python
"""
Offline tests for grbl_backend.py -- no plotter needed.

    python tests/test_grbl_backend.py
"""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

from fake_grbl import FakeGrbl, BANNER
from grbl_backend import GrblBackend, PlotStopped, usable_half
from plotter import PlotterError


def connected(fake=None, **cfg):
    fake = fake or FakeGrbl()
    b = GrblBackend(cfg, opener=lambda port: fake)
    b.connect("COM99")
    fake.sent.clear()
    fake.raw.clear()
    return b, fake


class TestPaper(unittest.TestCase):

    def test_letter_usable_area(self):
        hx, hy = usable_half()
        self.assertAlmostEqual(hx, 129.7)
        self.assertAlmostEqual(hy, 97.95)


class TestConnect(unittest.TestCase):

    def test_waits_for_banner_then_sets_units(self):
        fake = FakeGrbl()
        b = GrblBackend({}, opener=lambda port: fake)
        self.assertEqual(b.connect("COM99"), BANNER)
        self.assertEqual(fake.sent, ["G21", "G90"])
        self.assertTrue(b.connected)

    def test_no_banner_is_a_friendly_error_and_closes(self):
        fake = FakeGrbl(banner=False)
        b = GrblBackend({}, opener=lambda port: fake)
        with self.assertRaises(PlotterError) as cm:
            b.connect("COM99", banner_timeout=0.3)
        self.assertIn("didn't answer", str(cm.exception))
        self.assertFalse(b.connected)
        self.assertTrue(fake.closed)

    def test_port_in_use_mentions_candle(self):
        def opener(port):
            raise OSError("could not open port 'COM13': "
                          "PermissionError(13, 'Access is denied.')")
        b = GrblBackend({}, opener=opener)
        with self.assertRaises(PlotterError) as cm:
            b.connect("COM13")
        self.assertIn("Candle", str(cm.exception))

    def test_reconnect_clears_origin_and_pen_state(self):
        ports = [FakeGrbl(), FakeGrbl()]         # a real reopen resets the board
        b = GrblBackend({}, opener=lambda port: ports.pop(0))
        b.connect("COM99")
        b.set_origin()
        b.pen(True)
        b.connect("COM99")
        self.assertFalse(b.origin_set)
        self.assertFalse(b.is_down)

    def test_lost_connection_is_reported_and_clears_origin(self):
        b, fake = connected()
        b.set_origin()
        fake.fail_reads = True
        with self.assertRaises(PlotterError) as cm:
            b.wait()
        self.assertIn("Connection lost", str(cm.exception))
        self.assertFalse(b.connected)
        self.assertFalse(b.origin_set)


class TestPen(unittest.TestCase):

    def test_pen_down_waits_then_moves_servo_then_dwells(self):
        b, fake = connected()
        b.pen(True)
        self.assertEqual(fake.sent, ["G4 P0", "M3 S80", "G4 P0.30"])
        self.assertTrue(b.is_down)

    def test_pen_down_twice_sends_nothing_the_second_time(self):
        b, fake = connected()
        b.pen(True)
        fake.sent.clear()
        b.pen(True)
        self.assertEqual(fake.sent, [])

    def test_pen_up_is_m5(self):
        b, fake = connected()
        b.pen(True)
        fake.sent.clear()
        b.pen(False)
        self.assertEqual(fake.sent, ["G4 P0", "M5", "G4 P0.30"])

    def test_config_values_are_used(self):
        b, fake = connected(pen_down_s=95, servo_wait_s=0.5)
        b.pen(True)
        self.assertEqual(fake.sent, ["G4 P0", "M3 S95", "G4 P0.50"])

    def test_servo_to_touch_position(self):
        b, fake = connected()
        b.servo(b.pen_touch_s)
        self.assertEqual(fake.sent, ["G4 P0", "M3 S60", "G4 P0.30"])


class TestMotion(unittest.TestCase):

    def test_move_inside_paper(self):
        b, fake = connected()
        b.move(10, -5, 1500)
        self.assertEqual(fake.sent, ["G1 X10.000 Y-5.000 F1500"])

    def test_move_off_paper_raises_and_sends_nothing(self):
        b, fake = connected()
        with self.assertRaises(PlotterError) as cm:
            b.move(130.0, 0, 1500)
        self.assertIn("off the paper", str(cm.exception))
        self.assertEqual(fake.sent, [])

    def test_move_exactly_on_the_edge_is_allowed(self):
        b, fake = connected()
        b.move(129.7, -97.95, 1500)
        self.assertEqual(len(fake.sent), 1)

    def test_wait_is_g4_p0(self):
        b, fake = connected()
        b.wait()
        self.assertEqual(fake.sent, ["G4 P0"])

    def test_set_origin(self):
        b, fake = connected()
        b.set_origin()
        self.assertEqual(fake.sent, ["G4 P0", "G92 X0 Y0"])
        self.assertTrue(b.origin_set)

    def test_jog_is_relative_and_returns_to_absolute(self):
        b, fake = connected()
        b.jog(10, 0)
        self.assertEqual(fake.sent,
                         ["G91", "G1 X10.000 Y0.000 F1500", "G90", "G4 P0"])

    def test_jog_lifts_the_pen_first(self):
        b, fake = connected()
        b.pen(True)
        fake.sent.clear()
        b.jog(0, -1)
        self.assertEqual(fake.sent[:3], ["G4 P0", "M5", "G4 P0.30"])


class TestReplies(unittest.TestCase):

    def test_error_reply_names_the_command(self):
        b, fake = connected(FakeGrbl(replies={"G1": ["error:22"]}))
        with self.assertRaises(PlotterError) as cm:
            b.move(1, 1, 1500)
        self.assertIn("G1 X1.000", str(cm.exception))
        self.assertIn("error:22", str(cm.exception))

    def test_alarm_raises_and_clears_origin(self):
        b, fake = connected(FakeGrbl(replies={"G1": ["ALARM: Abort during cycle"]}))
        b.set_origin()
        with self.assertRaises(PlotterError):
            b.move(1, 1, 1500)
        self.assertFalse(b.origin_set)

    def test_read_settings(self):
        fake = FakeGrbl(replies={"$$": ["$100=80.000 (x, step/mm)",
                                        "$101=80.000 (y, step/mm)",
                                        "$22=0 (homing cycle, bool)", "ok"]})
        b, fake = connected(fake)
        self.assertEqual(b.read_settings(), {100: 80.0, 101: 80.0, 22: 0.0})

    def test_write_setting(self):
        b, fake = connected()
        b.write_setting(100, 80.53)
        self.assertEqual(fake.sent, ["$100=80.530"])


class TestStopAndPause(unittest.TestCase):

    def test_stop_sends_feed_hold_then_reset(self):
        b, fake = connected()
        b.set_origin()
        b.pen(True)
        fake.raw.clear()
        b.stop()
        self.assertEqual(fake.raw, [b"!", b"\x18"])
        self.assertFalse(b.origin_set)
        self.assertFalse(b.is_down)

    def test_command_during_stop_raises_plotstopped(self):
        b, fake = connected()
        b._stopping = True
        with self.assertRaises(PlotStopped):
            b._cmd("G1 X1 Y1 F100")

    def test_stop_while_idle_recovers(self):
        b, fake = connected()
        b.set_origin()
        b.stop()
        fake.sent.clear()
        b.recover()
        self.assertEqual(fake.sent, ["$X", "G21", "G90"])
        self.assertFalse(b.origin_set)
        b.wait()                    # usable again, no PlotStopped

    def test_pause_and_resume_are_realtime_bytes(self):
        b, fake = connected()
        b.pause()
        b.resume()
        self.assertEqual(fake.raw, [b"!", b"~"])
        self.assertEqual(fake.sent, [])

    def test_pause_extends_the_deadline(self):
        slow = {"G4 P0": [""] * 10 + ["ok"]}
        b, fake = connected(FakeGrbl(replies=slow, read_delay=0.05))
        b.paused = True
        b._cmd("G4 P0", timeout=0.2)        # 0.55 s of silence: still fine
        b.paused = False
        with self.assertRaises(PlotterError):
            b._cmd("G4 P0", timeout=0.2)


class TestFinish(unittest.TestCase):

    def test_finish_lifts_pen_returns_to_origin_and_closes(self):
        b, fake = connected()
        b.set_origin()
        b.pen(True)
        fake.sent.clear()
        b.finish()
        self.assertEqual(fake.sent, ["G4 P0", "M5", "G4 P0.30",
                                     "G1 X0.000 Y0.000 F3000", "G4 P0"])
        self.assertTrue(fake.closed)
        self.assertFalse(b.connected)

    def test_finish_without_origin_does_not_move(self):
        b, fake = connected()
        b.finish()
        self.assertNotIn("G1 X0.000 Y0.000 F3000", fake.sent)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python tests/test_grbl_backend.py`
Expected: `ModuleNotFoundError: No module named 'grbl_backend'`

- [ ] **Step 4: Write the backend**

Create `grbl_backend.py`:

```python
"""
grbl_backend.py  -  talks to a GRBL pen plotter (the IKRANBIRD AX4).

Coordinates are millimetres on the paper with 0,0 at the paper centre.
The AX4 has no homing switches, so 0,0 is wherever the head was when
set_origin() ran.  Moves outside the paper are refused, never clamped.

Facts this relies on (measured 2026-10-04, see docs/HARDWARE_NOTES.md):
  * opening the port resets the board; "Grbl 0.9i ..." follows ~1.5 s later
  * G1 is acknowledged when queued; "G4 P0" answers only when motion stops
  * pen up = M5 (also the state after any reset), pen down = M3 S<n>
"""

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


def usable_half(paper=LETTER_MM, margin=10.0):
    """Half-width and half-height of the drawable area, in mm."""
    return ((paper[0] - 2 * margin) / 2, (paper[1] - 2 * margin) / 2)


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
        self.limits = usable_half(margin=float(config.get("margin_mm", 10.0)))
        self._opener = opener
        self.ser = None
        self.firmware = None
        self.is_down = False
        self.origin_set = False
        self.paused = False
        self._stopping = False

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
        hx, hy = self.limits
        if abs(x) > hx + 1e-6 or abs(y) > hy + 1e-6:
            raise PlotterError(
                "A move to (%.1f, %.1f) mm is off the paper (the limit is "
                "+/-%.1f x +/-%.1f mm)." % (x, y, hx, hy))
        self._cmd("G1 X%.3f Y%.3f F%d" % (x, y, feed))

    def wait(self):
        self._cmd("G4 P0")

    def set_origin(self):
        """The head's current position becomes the paper centre."""
        self._cmd("G4 P0")
        self._cmd("G92 X0 Y0")
        self.origin_set = True

    def jog(self, dx, dy, feed=1500):
        """Relative move with the pen up.  Not bounds-checked: used to find
        the centre of the sheet before the origin exists."""
        self.pen(False)
        self._cmd("G91")
        try:
            self._cmd("G1 X%.3f Y%.3f F%d" % (dx, dy, feed))
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
        """After stop(): wait for the reset banner, unlock, mm + absolute."""
        self._wait_banner(2.0)
        self._stopping = False
        self._cmd("$X")
        self._cmd("G21")
        self._cmd("G90")

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
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python tests/test_grbl_backend.py`
Expected: `Ran 29 tests ... OK`

- [ ] **Step 6: Checkpoint**

Run: `for f in tests/test_*.py; do python "$f" || break; done`
Expected: every file reports `OK` (45 existing + 29 new).

---

### Task 2: Plotter on the AX4 (live Thonny use)

**Files:**
- Modify: `plotter.py` (`__init__` near line 257, `_goto` 339-346, `penup`/`pendown` 350-359, `connect` 367, `prepare` 415, `finish` 499)
- Modify: `plotter_config.json`
- Test: `tests/test_plotter_grbl.py`

**Interfaces:**
- Consumes: `GrblBackend`, `FakeGrbl` from Task 1.
- Produces: `Plotter.grbl` (a `GrblBackend` or `None`), `Plotter.backend_name` (`"mini"` or `"grbl"` from config, default `"mini"`). On the AX4 path a turtle at (x, y) is sent to `(x * scale, y * scale)` mm.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_plotter_grbl.py`:

```python
"""
Offline tests: the Plotter turtle driving the AX4 through GrblBackend.

    python tests/test_plotter_grbl.py
"""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

import turtle
import grbl_backend
from fake_grbl import FakeGrbl
from grbl_backend import GrblBackend
from plotter import Plotter, PlotterError

CFG = {"backend": "grbl", "draw_feed": 1500, "travel_feed": 3000}


def grbl_plotter(fake):
    turtle.Screen().tracer(0)
    p = Plotter(show_paper=False, config=CFG)
    p.hideturtle()
    p.grbl = GrblBackend(CFG, opener=lambda port: fake)
    p.grbl.connect("COM99")
    p.prepare()
    fake.sent.clear()
    return p


class TestPlotterOnGrbl(unittest.TestCase):

    def test_backend_name_comes_from_config(self):
        turtle.Screen().tracer(0)
        self.assertEqual(Plotter(show_paper=False, config=CFG).backend_name, "grbl")
        self.assertEqual(Plotter(show_paper=False, config={}).backend_name, "mini")

    def test_prepare_sets_the_origin_without_moving(self):
        fake = FakeGrbl()
        p = grbl_plotter(fake)
        self.assertTrue(p.grbl.origin_set)

    def test_forward_draws_in_mm_and_waits(self):
        fake = FakeGrbl()
        p = grbl_plotter(fake)
        p.forward(100)                       # 100 steps * 0.25 = 25 mm
        self.assertEqual(fake.sent, ["G4 P0", "M3 S80", "G4 P0.30",
                                     "G1 X25.000 Y0.000 F1500", "G4 P0"])

    def test_penup_travel_uses_travel_feed(self):
        fake = FakeGrbl()
        p = grbl_plotter(fake)
        p.penup()
        p.goto(0, 100)
        self.assertEqual(fake.sent, ["G1 X0.000 Y25.000 F3000", "G4 P0"])

    def test_pendown_after_penup_lowers_the_pen(self):
        fake = FakeGrbl()
        p = grbl_plotter(fake)
        p.penup()
        fake.sent.clear()
        p.pendown()
        self.assertEqual(fake.sent, ["G4 P0", "M3 S80", "G4 P0.30"])

    def test_off_paper_move_raises(self):
        fake = FakeGrbl()
        p = grbl_plotter(fake)
        p.penup()
        with self.assertRaises(PlotterError):
            p.goto(1000, 0)                  # 250 mm: off the Letter sheet

    def test_finish_lifts_returns_and_closes(self):
        fake = FakeGrbl()
        p = grbl_plotter(fake)
        p.forward(40)
        fake.sent.clear()
        p.finish()
        self.assertEqual(fake.sent, ["G4 P0", "M5", "G4 P0.30",
                                     "G1 X0.000 Y0.000 F3000", "G4 P0"])
        self.assertIsNone(p.grbl)
        self.assertTrue(fake.closed)

    def test_connect_builds_a_grbl_backend(self):
        fake = FakeGrbl()
        saved = grbl_backend._default_opener
        grbl_backend._default_opener = lambda port: fake
        try:
            turtle.Screen().tracer(0)
            p = Plotter(show_paper=False, config=CFG)
            p.connect("COM99")
            self.assertIsInstance(p.grbl, GrblBackend)
            self.assertEqual(fake.sent, ["G21", "G90"])
        finally:
            grbl_backend._default_opener = saved


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python tests/test_plotter_grbl.py`
Expected: FAIL / ERROR, first one `AttributeError: 'Plotter' object has no attribute 'backend_name'`

- [ ] **Step 3: Add the AX4 path to `plotter.py`**

In `Plotter.__init__`, after the line `self.firmware = None`, add:

```python
        self.grbl = None             # GrblBackend when driving the AX4
        self.backend_name = self.config.get("backend", "mini")
```

In `_goto`, replace the block

```python
        # hardware first, then screen, so the pen never runs ahead of code
        if self.ser is not None:
```

with

```python
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
```

(the indented MINI block underneath stays exactly as it is).

Replace `penup` and `pendown` with:

```python
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
```

At the top of `connect()`, directly after the docstring, add:

```python
        if getattr(self, "backend_name", "mini") == "grbl":
            from grbl_backend import GrblBackend
            print("Connecting to the AX4 plotter ...")
            self.grbl = GrblBackend(self.config)
            self.firmware = self.grbl.connect(port)
            print("Connected.  Nothing has moved yet.")
            return self.firmware
```

At the top of `prepare()`, directly after the docstring, add:

```python
        if getattr(self, "grbl", None) is not None:
            # The AX4 has no homing: wherever the pen is now is the centre.
            self.grbl.pen(False)
            self.grbl.set_origin()
            print("Ready.  The pen's current position is the centre of "
                  "the paper.")
            return
```

At the top of `finish()`, directly after the docstring, add:

```python
        if getattr(self, "grbl", None) is not None:
            try:
                self.grbl.finish(self.travel_feed)
            finally:
                self.grbl = None
            print("Done.  Pen up, head back at the centre.")
            return
```

- [ ] **Step 4: Point the config at the AX4**

Replace the whole of `plotter_config.json` with:

```json
{
  "_comment": "Written by the calibration tools. Students never edit this.",
  "_status": "backend grbl = IKRANBIRD AX4. The Z values are MINI air-test values, unused by the AX4.",
  "backend": "grbl",
  "calibrated": null,
  "draw_feed": 1500,
  "margin_mm": 10,
  "paper": "letter",
  "pen_down_s": 80,
  "pen_down_z": 10.0,
  "pen_offset": [0.0, 0.0],
  "pen_setup_done": "2026-10-04",
  "pen_touch_s": 60,
  "pen_up_z": 15.0,
  "servo_wait_s": 0.3,
  "travel_feed": 3000
}
```

(`pen_setup_done` is today's date because the pen was set up by hand this session: touch S60, down S80.)

- [ ] **Step 5: Run the new tests**

Run: `python tests/test_plotter_grbl.py`
Expected: `Ran 8 tests ... OK`

- [ ] **Step 6: Checkpoint**

Run: `for f in tests/test_*.py; do python "$f" || break; done`
Expected: all OK, including the 45 original tests unchanged.

---

### Task 3: Student-file runner

**Files:**
- Create: `run_turtle.py`
- Create: `tests/samples/square.py`, `module_level.py`, `two_turtles.py`, `typo.py`, `syntax_error.py`, `asks_input.py`, `fill_write_colour.py`, `prints.py`, `nothing.py`
- Test: `tests/test_run_turtle.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: command `python run_turtle.py <file.py>` printing exactly one JSON object `{"strokes": [[[x, y], ...], ...], "warnings": [str], "error": null | {"type": str, "message": str, "line": int | null}}` in **turtle units**. Warning strings are the module constants `W_FILL`, `W_WRITE`, `W_DOT`, `W_COLOUR`. Error type for `input()` is `"KeyboardInputNotSupported"`.

- [ ] **Step 1: Write the sample student programs**

`tests/samples/square.py`:

```python
import turtle

t = turtle.Turtle()
for i in range(4):
    t.forward(100)
    t.left(90)
turtle.done()
```

`tests/samples/module_level.py`:

```python
from turtle import *

forward(50)
penup()
goto(0, 100)
pendown()
forward(20)
done()
```

`tests/samples/two_turtles.py`:

```python
import turtle

a = turtle.Turtle()
b = turtle.Turtle()
a.forward(10)
b.left(90)
b.forward(10)
a.forward(10)
```

`tests/samples/typo.py`:

```python
import turtle

t = turtle.Turtle()
t.forward(50)
t.forwad(10)
```

`tests/samples/syntax_error.py`:

```python
import turtle
turtle.forward(10
```

`tests/samples/asks_input.py`:

```python
import turtle

size = int(input("How big? "))
turtle.forward(size)
```

`tests/samples/fill_write_colour.py`:

```python
import turtle

t = turtle.Turtle()
t.begin_fill()
t.forward(20)
t.left(90)
t.forward(20)
t.end_fill()
t.write("hi")
t.pencolor("red")
t.penup()
t.goto(0, -50)
t.pendown()
t.forward(20)
```

`tests/samples/prints.py`:

```python
import turtle

print('{"not": "json"')
print("hello }")
turtle.forward(10)
```

`tests/samples/nothing.py`:

```python
import turtle

t = turtle.Turtle()
t.penup()
t.forward(100)
```

- [ ] **Step 2: Write the failing tests**

Create `tests/test_run_turtle.py`:

```python
"""
Tests for run_turtle.py: runs sample student programs in a subprocess,
exactly as the dashboard does.

    python tests/test_run_turtle.py
"""

import json
import os
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
RUNNER = os.path.join(ROOT, "run_turtle.py")
SAMPLES = os.path.join(HERE, "samples")

sys.path.insert(0, ROOT)
import run_turtle


def run_sample(name):
    out = subprocess.run([sys.executable, RUNNER, os.path.join(SAMPLES, name)],
                         capture_output=True, text=True, encoding="utf-8",
                         timeout=60)
    return json.loads(out.stdout)


class TestRunner(unittest.TestCase):

    def test_object_style_square(self):
        r = run_sample("square.py")
        self.assertIsNone(r["error"])
        self.assertEqual(len(r["strokes"]), 1)
        s = r["strokes"][0]
        self.assertEqual(len(s), 5)
        self.assertEqual(s[0], [0, 0])
        self.assertEqual(s[1], [100, 0])
        self.assertAlmostEqual(s[2][1], 100, places=3)

    def test_module_level_functions_record(self):
        r = run_sample("module_level.py")
        self.assertIsNone(r["error"])
        self.assertEqual(r["strokes"], [[[0, 0], [50, 0]],
                                        [[0, 100], [20, 100]]])

    def test_two_turtles_keep_code_order(self):
        r = run_sample("two_turtles.py")
        s = r["strokes"]
        self.assertEqual(len(s), 3)
        self.assertEqual(s[0], [[0, 0], [10, 0]])
        self.assertAlmostEqual(s[1][1][1], 10, places=3)     # b went up
        self.assertEqual(s[2], [[10, 0], [20, 0]])

    def test_runtime_error_keeps_partial_drawing(self):
        r = run_sample("typo.py")
        self.assertEqual(r["error"]["type"], "AttributeError")
        self.assertEqual(r["error"]["line"], 5)
        self.assertEqual(r["strokes"], [[[0, 0], [50, 0]]])

    def test_syntax_error_has_a_line(self):
        r = run_sample("syntax_error.py")
        self.assertEqual(r["error"]["type"], "SyntaxError")
        self.assertIn(r["error"]["line"], (2, 3))
        self.assertEqual(r["strokes"], [])

    def test_input_is_refused_clearly(self):
        r = run_sample("asks_input.py")
        self.assertEqual(r["error"]["type"], "KeyboardInputNotSupported")
        self.assertIn("keyboard input", r["error"]["message"])

    def test_fill_write_and_colours_warn(self):
        r = run_sample("fill_write_colour.py")
        self.assertIsNone(r["error"])
        self.assertIn(run_turtle.W_FILL, r["warnings"])
        self.assertIn(run_turtle.W_WRITE, r["warnings"])
        self.assertIn(run_turtle.W_COLOUR, r["warnings"])
        self.assertEqual(len(r["strokes"]), 2)

    def test_student_print_does_not_corrupt_json(self):
        r = run_sample("prints.py")
        self.assertIsNone(r["error"])
        self.assertEqual(r["strokes"], [[[0, 0], [10, 0]]])

    def test_program_that_draws_nothing(self):
        r = run_sample("nothing.py")
        self.assertIsNone(r["error"])
        self.assertEqual(r["strokes"], [])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python tests/test_run_turtle.py`
Expected: `ModuleNotFoundError: No module named 'run_turtle'`

- [ ] **Step 4: Write the runner**

Create `run_turtle.py`:

```python
"""
run_turtle.py  -  run a student's turtle program and record what it draws.

    python run_turtle.py student.py

Prints ONE JSON object on stdout:

    {"strokes": [[[x, y], ...], ...],      turtle units, in drawing order
     "warnings": ["...", ...],
     "error": null or {"type": ..., "message": ..., "line": n or null}}

Student code is ordinary turtle code: `import turtle` or
`from turtle import *`.  Before it runs, turtle.Turtle is swapped for a
turtle that records every pen-down line, the window is hidden, and
done()/mainloop()/exitonclick() do nothing.  The student's own print()
output goes to stderr so it cannot spoil the JSON.

The dashboard runs this in a separate process with a time limit, so a
crash or a loop that never ends cannot freeze the dashboard.
"""

import builtins
import json
import os
import runpy
import sys
import traceback
import turtle

W_FILL = "Fill is drawn as an outline only."
W_WRITE = "Text from write() is not drawn."
W_DOT = "dot() and stamp() are not drawn."
W_COLOUR = "The plotter has one pen: all lines are drawn in the same colour."

STROKES = []
WARNINGS = []
_COLOURS = set()
_last = [None]               # the turtle that drew most recently


def _warn(msg):
    if msg not in WARNINGS:
        WARNINGS.append(msg)


class RecordingTurtle(turtle.Turtle):
    """A normal turtle that also records every pen-down line."""

    def __init__(self, *args, **kwargs):
        self._stroke = None
        super().__init__(*args, **kwargs)

    def _goto(self, end):
        if self.isdown():
            # A new stroke when this turtle starts drawing, or when another
            # turtle drew in between, so strokes stay in code order.
            if self._stroke is None or _last[0] is not self:
                x, y = self.pos()
                self._stroke = [[round(x, 3), round(y, 3)]]
                STROKES.append(self._stroke)
                _COLOURS.add(str(self.pencolor()))
            self._stroke.append([round(end[0], 3), round(end[1], 3)])
            _last[0] = self
        else:
            self._stroke = None
        super()._goto(end)

    def penup(self):
        super().penup()
        self._stroke = None

    # turtle binds these aliases at class-creation time
    pu = up = penup

    def begin_fill(self):
        _warn(W_FILL)
        super().begin_fill()

    def write(self, *args, **kwargs):
        _warn(W_WRITE)
        return super().write(*args, **kwargs)

    def dot(self, *args, **kwargs):
        _warn(W_DOT)
        return super().dot(*args, **kwargs)

    def stamp(self):
        _warn(W_DOT)
        return super().stamp()


class KeyboardInputNotSupported(Exception):
    pass


def _noop(*args, **kwargs):
    return None


def _no_input(*args, **kwargs):
    raise KeyboardInputNotSupported(
        "This program asks for keyboard input, which the plotter can't do.")


def install():
    """Swap the recording turtle in and keep the window quiet and hidden."""
    turtle.Turtle = RecordingTurtle
    turtle.Pen = RecordingTurtle
    screen = turtle.Screen()
    screen.tracer(0)
    screen.getcanvas().winfo_toplevel().withdraw()
    turtle.TurtleScreen.tracer = _noop
    turtle.TurtleScreen.delay = _noop
    turtle.TurtleScreen.mainloop = _noop
    turtle.TurtleScreen.textinput = _no_input
    turtle.TurtleScreen.numinput = _no_input
    turtle._Screen.exitonclick = _noop
    for name in ("done", "mainloop", "exitonclick", "tracer", "delay"):
        setattr(turtle, name, _noop)
    turtle.textinput = _no_input
    turtle.numinput = _no_input
    builtins.input = _no_input


def _student_line(exc, path):
    """The line in the student's file where things went wrong."""
    if isinstance(exc, SyntaxError) and exc.lineno:
        return exc.lineno
    target = os.path.normcase(os.path.abspath(path))
    line = None
    for frame in traceback.extract_tb(exc.__traceback__):
        if os.path.normcase(os.path.abspath(frame.filename)) == target:
            line = frame.lineno
    return line


def run(path):
    error = None
    real_stdout = sys.stdout
    sys.stdout = sys.stderr          # student print() must not spoil the JSON
    try:
        install()
        runpy.run_path(path, run_name="__main__")
    except SystemExit:
        pass
    except BaseException as e:
        error = {"type": type(e).__name__, "message": str(e),
                 "line": _student_line(e, path)}
    finally:
        sys.stdout = real_stdout
    if len(_COLOURS) > 1:
        _warn(W_COLOUR)
    return {"strokes": [s for s in STROKES if len(s) >= 2],
            "warnings": WARNINGS, "error": error}


def main(argv):
    if len(argv) != 2:
        result = {"strokes": [], "warnings": [],
                  "error": {"type": "Usage", "line": None,
                            "message": "usage: python run_turtle.py student.py"}}
    else:
        result = run(argv[1])
    sys.stdout.write(json.dumps(result))
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python tests/test_run_turtle.py`
Expected: `Ran 9 tests ... OK` (slower than other suites: each test starts a Python process).

- [ ] **Step 6: Checkpoint**

Run: `for f in tests/test_*.py; do python "$f" || break; done`
Expected: all OK.

---

### Task 4: Dashboard logic

**Files:**
- Create: `dashboard_logic.py`
- Test: `tests/test_dashboard_logic.py`

**Interfaces:**
- Consumes: `LETTER_MM`, `usable_half`, `PlotStopped` from `grbl_backend`; `run_turtle.py` as a command; `GrblBackend` + `FakeGrbl` in tests.
- Produces:
  - constants `STEP_MM = 0.25`, `MAX_SCALE = 1000`, `STUDENT_TIMEOUT = 20`, `CAL_MM = 150.0`, `AX4_DEFAULTS` (dict)
  - `ax4_config(raw: dict) -> dict`
  - `run_student(path, timeout=STUDENT_TIMEOUT) -> dict` (runner JSON shape)
  - `error_text(err: dict | None) -> str`
  - `to_mm(strokes, scale_pct) -> list[list[(x, y)]]`
  - `inside(point, half) -> bool`, `fits(strokes_mm, half) -> bool`
  - `fit_scale(strokes_turtle, half) -> int`
  - `size_mm(strokes_mm) -> (w, h)`
  - `estimate_seconds(strokes_mm, draw_feed, travel_feed, pen_s=0.3, per_seg=0.05) -> float`
  - `format_time(seconds) -> str`
  - `class Checklist(config)` with `connected`, `origin_set`, `pen_setup_done`, `calibrated`, `problems() -> list[str]`, `can_plot`, `banner`
  - `plot_blocker(checklist, strokes_mm, half) -> str | None`
  - `calibration_result(current, measured_x, measured_y, target=CAL_MM) -> (new: float, differ: bool)` (raises `ValueError` outside 140-160 mm)
  - `calibration_strokes() -> strokes_mm`, `zigzag_strokes() -> strokes_mm`
  - `plot_strokes(backend, strokes_mm, draw_feed, travel_feed, progress=None)`
  - `svg_text(strokes_mm, paper=LETTER_MM) -> str`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_dashboard_logic.py`:

```python
"""
Tests for dashboard_logic.py -- no window, no plotter.

    python tests/test_dashboard_logic.py
"""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

import dashboard_logic as logic
from fake_grbl import FakeGrbl
from grbl_backend import GrblBackend, usable_half

HALF = usable_half()                     # (129.7, 97.95)
SAMPLES = os.path.join(HERE, "samples")


class TestScale(unittest.TestCase):

    def test_100_percent_is_quarter_mm_per_step(self):
        self.assertEqual(logic.to_mm([[(0, 0), (100, -40)]], 100),
                         [[(0.0, 0.0), (25.0, -10.0)]])

    def test_200_percent_doubles(self):
        self.assertEqual(logic.to_mm([[(0, 0), (100, 0)]], 200)[0][1], (50.0, 0.0))

    def test_fits_and_inside(self):
        self.assertTrue(logic.fits([[(0, 0), (129.7, 97.95)]], HALF))
        self.assertFalse(logic.fits([[(0, 0), (130, 0)]], HALF))
        self.assertFalse(logic.inside((0, -98), HALF))

    def test_fit_scale_uses_the_tighter_axis(self):
        # x extent 600 steps -> 129.7 / (600*0.25) = 86.4%; y 100 -> 391%
        self.assertEqual(logic.fit_scale([[(-600, 0), (600, 100)]], HALF), 86)

    def test_fit_scale_result_actually_fits(self):
        strokes = [[(-333, -271), (517, 389)]]
        pct = logic.fit_scale(strokes, HALF)
        self.assertTrue(logic.fits(logic.to_mm(strokes, pct), HALF))
        self.assertFalse(logic.fits(logic.to_mm(strokes, pct + 1), HALF))

    def test_fit_scale_is_capped(self):
        self.assertEqual(logic.fit_scale([[(0, 0), (1, 0)]], HALF), logic.MAX_SCALE)

    def test_size(self):
        self.assertEqual(logic.size_mm([[(-10, 5), (30, -15)]]), (40, 20))


class TestEmpty(unittest.TestCase):

    def test_empty_drawing(self):
        self.assertEqual(logic.fit_scale([], HALF), 100)
        self.assertEqual(logic.size_mm([]), (0, 0))
        self.assertEqual(logic.estimate_seconds([], 1500, 3000), 0)
        c = logic.Checklist({"pen_setup_done": "2026-10-04"})
        c.connected = c.origin_set = True
        self.assertEqual(logic.plot_blocker(c, [], HALF),
                         "Nothing to plot - open a student file first.")


class TestTime(unittest.TestCase):

    def test_one_line(self):
        # 25 mm at 25 mm/s = 1 s, + 0.05 per segment, + 2 x 0.3 pen,
        # + 25 mm back to the origin at 50 mm/s = 0.5 s
        t = logic.estimate_seconds([[(0, 0), (25, 0)]], 1500, 3000)
        self.assertAlmostEqual(t, 2.15)

    def test_format(self):
        self.assertEqual(logic.format_time(42.4), "42 s")
        self.assertEqual(logic.format_time(65), "1 min 05 s")


class TestChecklist(unittest.TestCase):

    def test_fresh_session_needs_connect_and_origin(self):
        c = logic.Checklist({"pen_setup_done": "2026-10-04", "calibrated": None})
        self.assertFalse(c.can_plot)
        self.assertEqual(c.problems(), [
            "Connect to the plotter.",
            "Set the origin (head over the centre of the sheet)."])

    def test_pen_setup_required(self):
        c = logic.Checklist({})
        c.connected = c.origin_set = True
        self.assertEqual(c.problems(), ["Run Pen setup."])

    def test_calibration_does_not_block_but_shows_banner(self):
        c = logic.Checklist({"pen_setup_done": "x", "calibrated": None})
        c.connected = c.origin_set = True
        self.assertTrue(c.can_plot)
        self.assertIn("NOT CALIBRATED", c.banner)
        c.calibrated = "2026-11-01"
        self.assertEqual(c.banner, "")

    def test_blocker_for_off_paper(self):
        c = logic.Checklist({"pen_setup_done": "x"})
        c.connected = c.origin_set = True
        self.assertEqual(logic.plot_blocker(c, [[(0, 0), (200, 0)]], HALF),
                         "Drawing doesn't fit - use Fit to paper or a smaller scale.")
        self.assertIsNone(logic.plot_blocker(c, [[(0, 0), (20, 0)]], HALF))


class TestCalibration(unittest.TestCase):

    def test_short_lines_mean_more_steps(self):
        new, differ = logic.calibration_result(80.0, 149.0, 149.0)
        self.assertAlmostEqual(new, 80.537, places=3)
        self.assertFalse(differ)

    def test_x_and_y_are_averaged_and_flagged(self):
        new, differ = logic.calibration_result(80.0, 147.0, 151.0)
        self.assertAlmostEqual(new, round((80 * 150 / 147 + 80 * 150 / 151) / 2, 3))
        self.assertTrue(differ)

    def test_silly_measurements_are_refused(self):
        with self.assertRaises(ValueError):
            logic.calibration_result(80.0, 15.0, 150.0)

    def test_calibration_l_fits_and_is_150mm(self):
        s = logic.calibration_strokes()
        self.assertTrue(logic.fits(s, HALF))
        corner, x_end, y_end = s[0][1], s[0][0], s[0][2]
        self.assertEqual(x_end[0] - corner[0], 150)
        self.assertEqual(y_end[1] - corner[1], 150)

    def test_zigzag_is_three_separate_strokes_40mm_wide(self):
        z = logic.zigzag_strokes()
        self.assertEqual(len(z), 3)
        self.assertEqual(logic.size_mm(z)[0], 40)


class TestPlotStrokes(unittest.TestCase):

    def test_order_travel_wait_pen_draw(self):
        fake = FakeGrbl()
        b = GrblBackend({}, opener=lambda port: fake)
        b.connect("COM99")
        b.set_origin()
        fake.sent.clear()
        seen = []
        logic.plot_strokes(b, [[(10, 0), (20, 0)]], 1500, 3000,
                           progress=lambda i, n: seen.append((i, n)))
        self.assertEqual(fake.sent, [
            "G1 X10.000 Y0.000 F3000", "G4 P0",          # travel, arrive
            "G4 P0", "M3 S80", "G4 P0.30",               # pen down
            "G1 X20.000 Y0.000 F1500", "G4 P0",          # draw, finish line
            "G4 P0", "M5", "G4 P0.30",                   # pen up
            "G1 X0.000 Y0.000 F3000", "G4 P0"])          # home to origin
        self.assertEqual(seen, [(1, 1)])


class TestSvg(unittest.TestCase):

    def test_centre_maps_to_middle_of_sheet(self):
        text = logic.svg_text([[(0, 0), (10, 10)]])
        self.assertIn('width="279.4mm"', text)
        self.assertIn("M 139.700,107.950 L 149.700,97.950", text)


class TestRunStudent(unittest.TestCase):

    def test_good_file(self):
        r = logic.run_student(os.path.join(SAMPLES, "square.py"))
        self.assertIsNone(r["error"])
        self.assertEqual(len(r["strokes"]), 1)

    def test_endless_loop_is_stopped(self):
        path = os.path.join(SAMPLES, "forever.py")
        r = logic.run_student(path, timeout=3)
        self.assertEqual(r["error"]["type"], "Timeout")
        self.assertIn("too long", logic.error_text(r["error"]))

    def test_error_text(self):
        self.assertEqual(logic.error_text(None), "")
        self.assertEqual(
            logic.error_text({"type": "NameError", "line": 4,
                              "message": "name 'forwad' is not defined"}),
            "Line 4: NameError: name 'forwad' is not defined")


if __name__ == "__main__":
    unittest.main()
```

Also create `tests/samples/forever.py`:

```python
import turtle

while True:
    turtle.left(1)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python tests/test_dashboard_logic.py`
Expected: `ModuleNotFoundError: No module named 'dashboard_logic'`

- [ ] **Step 3: Write the logic module**

Create `dashboard_logic.py`:

```python
"""
dashboard_logic.py  -  everything the AX4 dashboard decides, with no Tkinter.

Kept apart from dashboard.py so it can be tested without a window.
Units: run_turtle.py gives turtle units; everything else here is mm on the
paper, with 0,0 at the paper centre.
"""

import json
import math
import os
import subprocess
import sys

from grbl_backend import LETTER_MM

STEP_MM = 0.25               # 100% scale: one turtle step = 0.25 mm
MAX_SCALE = 1000
STUDENT_TIMEOUT = 20         # seconds a student program may run
CAL_MM = 150.0               # length of each calibration line
RUNNER = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                      "run_turtle.py")

AX4_DEFAULTS = {
    "backend": "grbl", "paper": "letter", "margin_mm": 10,
    "pen_touch_s": 60, "pen_down_s": 80, "servo_wait_s": 0.3,
    "draw_feed": 1500, "travel_feed": 3000,
    "pen_setup_done": None, "calibrated": None,
}

_PLAIN_ERRORS = ("Timeout", "KeyboardInputNotSupported", "RunnerFailed")


def ax4_config(raw):
    """The config file's values on top of AX4_DEFAULTS."""
    cfg = dict(AX4_DEFAULTS)
    cfg.update(raw)
    return cfg


# ---- running student code --------------------------------------------------

def _failed(kind, message):
    return {"strokes": [], "warnings": [],
            "error": {"type": kind, "message": message, "line": None}}


def run_student(path, timeout=STUDENT_TIMEOUT):
    """Run a student's .py in a separate process and return what it drew."""
    flags = 0x08000000 if sys.platform == "win32" else 0   # no console window
    try:
        out = subprocess.run([sys.executable, RUNNER, path],
                             capture_output=True, text=True, encoding="utf-8",
                             errors="replace", timeout=timeout,
                             creationflags=flags)
    except subprocess.TimeoutExpired:
        return _failed("Timeout", "The program took too long - is there a "
                                  "loop that never ends?")
    try:
        return json.loads(out.stdout)
    except ValueError:
        last = (out.stderr.strip().splitlines() or
                ["The program could not be run."])[-1]
        return _failed("RunnerFailed", last)


def error_text(err):
    if not err:
        return ""
    if err["type"] in _PLAIN_ERRORS:
        return err["message"]
    where = "Line %d: " % err["line"] if err.get("line") else ""
    return "%s%s: %s" % (where, err["type"], err["message"])


# ---- scale and paper -------------------------------------------------------

def to_mm(strokes, scale_pct):
    k = STEP_MM * scale_pct / 100.0
    return [[(x * k, y * k) for x, y in s] for s in strokes]


def inside(point, half):
    return abs(point[0]) <= half[0] + 1e-9 and abs(point[1]) <= half[1] + 1e-9


def fits(strokes_mm, half):
    return all(inside(p, half) for s in strokes_mm for p in s)


def fit_scale(strokes, half):
    """Largest whole percentage at which the drawing fits the paper."""
    ax = max((abs(x) for s in strokes for x, _ in s), default=0)
    ay = max((abs(y) for s in strokes for _, y in s), default=0)
    limits = []
    if ax > 0:
        limits.append(half[0] / (ax * STEP_MM) * 100)
    if ay > 0:
        limits.append(half[1] / (ay * STEP_MM) * 100)
    if not limits:
        return 100
    return max(1, min(MAX_SCALE, int(math.floor(min(limits) + 1e-9))))


def size_mm(strokes_mm):
    xs = [x for s in strokes_mm for x, _ in s]
    ys = [y for s in strokes_mm for _, y in s]
    if not xs:
        return (0, 0)
    return (max(xs) - min(xs), max(ys) - min(ys))


def estimate_seconds(strokes_mm, draw_feed, travel_feed, pen_s=0.3,
                     per_seg=0.05):
    t = 0.0
    pos = (0.0, 0.0)
    for s in strokes_mm:
        t += math.dist(pos, s[0]) / (travel_feed / 60.0)
        for a, b in zip(s, s[1:]):
            t += math.dist(a, b) / (draw_feed / 60.0) + per_seg
        t += 2 * pen_s
        pos = s[-1]
    if strokes_mm:
        t += math.dist(pos, (0.0, 0.0)) / (travel_feed / 60.0)
    return t


def format_time(seconds):
    s = int(round(seconds))
    if s < 60:
        return "%d s" % s
    return "%d min %02d s" % (s // 60, s % 60)


# ---- setup checklist -------------------------------------------------------

class Checklist:

    def __init__(self, config):
        self.connected = False
        self.origin_set = False
        self.pen_setup_done = config.get("pen_setup_done")
        self.calibrated = config.get("calibrated")

    def problems(self):
        out = []
        if not self.connected:
            out.append("Connect to the plotter.")
        if not self.pen_setup_done:
            out.append("Run Pen setup.")
        if not self.origin_set:
            out.append("Set the origin (head over the centre of the sheet).")
        return out

    @property
    def can_plot(self):
        return not self.problems()

    @property
    def banner(self):
        if self.calibrated:
            return ""
        return ("NOT CALIBRATED - distances may be slightly off.  Run "
                "'Calibrate distances...' when you can.")


def plot_blocker(checklist, strokes_mm, half):
    """Why Plot is disabled, or None if it can go."""
    problems = checklist.problems()
    if problems:
        return problems[0]
    if not strokes_mm:
        return "Nothing to plot - open a student file first."
    if not fits(strokes_mm, half):
        return "Drawing doesn't fit - use Fit to paper or a smaller scale."
    return None


# ---- calibration and test drawings -----------------------------------------

def calibration_result(current, measured_x, measured_y, target=CAL_MM):
    """New steps/mm for both axes, and whether X and Y disagreed by > 1%.

    The AX4 is CoreXY: GRBL assumes both motors share one steps/mm, so the
    two results are averaged and used for $100 and $101 alike.
    """
    for m in (measured_x, measured_y):
        if not 140 <= m <= 160:
            raise ValueError("The lines should measure between 140 and "
                             "160 mm - please measure again.")
    nx = current * target / measured_x
    ny = current * target / measured_y
    new = round((nx + ny) / 2, 3)
    return new, abs(nx - ny) / new > 0.01


def calibration_strokes():
    """An L: 150 mm along X and 150 mm up Y from the corner, end ticks."""
    a, b, t = -CAL_MM / 2, CAL_MM / 2, 2.5
    return [
        [(b, a), (a, a), (a, b)],        # X end -> corner -> Y end
        [(b, a - t), (b, a + t)],        # tick at the end of the X line
        [(a - t, b), (a + t, b)],        # tick at the end of the Y line
    ]


def zigzag_strokes():
    """Three small zigzags, 40 mm wide in all, for the pen test."""
    out = []
    for i in range(3):
        x0 = -20 + i * 15
        out.append([(x0 + j * 2.5, 0.0 if j % 2 == 0 else 6.0)
                    for j in range(5)])
    return out


# ---- plotting --------------------------------------------------------------

def plot_strokes(backend, strokes_mm, draw_feed, travel_feed, progress=None):
    """Draw strokes in order; finish with the pen up at the origin."""
    n = len(strokes_mm)
    for i, s in enumerate(strokes_mm, 1):
        backend.pen(False)
        backend.move(s[0][0], s[0][1], travel_feed)
        backend.wait()                   # arrive before the pen drops
        backend.pen(True)
        for x, y in s[1:]:
            backend.move(x, y, draw_feed)
        backend.wait()                   # finish the line before lifting
        if progress:
            progress(i, n)
    backend.pen(False)
    backend.move(0.0, 0.0, travel_feed)
    backend.wait()


def svg_text(strokes_mm, paper=LETTER_MM):
    w, h = paper
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<svg xmlns="http://www.w3.org/2000/svg" width="%gmm" '
             'height="%gmm" viewBox="0 0 %g %g">' % (w, h, w, h)]
    for s in strokes_mm:
        pts = " L ".join("%.3f,%.3f" % (x + w / 2, h / 2 - y) for x, y in s)
        lines.append('  <path d="M %s" fill="none" stroke="black" '
                     'stroke-width="0.4" stroke-linecap="round" '
                     'stroke-linejoin="round"/>' % pts)
    lines.append("</svg>")
    return "\n".join(lines) + "\n"
```

Note on `test_order_travel_wait_pen_draw`: `backend.pen(False)` at the start is a no-op (pen already up), so the first line sent is the travel move.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python tests/test_dashboard_logic.py`
Expected: `Ran 24 tests ... OK`

- [ ] **Step 5: Checkpoint**

Run: `for f in tests/test_*.py; do python "$f" || break; done`
Expected: all OK.

---

### Task 5: Dashboard window

**Files:**
- Create: `dashboard.py`
- Test: `tests/test_dashboard_smoke.py`

**Interfaces:**
- Consumes: everything in `dashboard_logic`; `GrblBackend`, `PlotStopped`, `usable_half`, `LETTER_MM`; `load_config`, `save_config`, `PlotterError` from `plotter`; `PenSetupWizard`, `CalibrationWizard` from Task 6 (imported lazily inside the two button handlers so this task stands alone).
- Produces: `class Dashboard(root, backend=None)` with attributes `config`, `raw_config`, `half`, `backend`, `port` (None = auto-detect), `check`, `strokes`, `result`, `path`, `plotting`, `paused`, and methods used by the wizards: `refresh()`, `start_job(strokes_mm, label, on_done=None)`, `save_setting(**values)`, `mark_pen_setup()`, `mark_calibrated()`, `load_file(path)`. `main()` opens the window.

- [ ] **Step 1: Write the failing smoke test**

Create `tests/test_dashboard_smoke.py`:

```python
"""
Smoke tests: build the dashboard window against the fake port and press a
few buttons.  No plotter, but needs a display (fine on the teacher laptop).

    python tests/test_dashboard_smoke.py
"""

import os
import sys
import time
import tkinter as tk
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

import dashboard
from fake_grbl import FakeGrbl
from grbl_backend import GrblBackend

SAMPLES = os.path.join(HERE, "samples")


def make(fake, save=False):
    root = tk.Tk()
    root.withdraw()
    b = GrblBackend({}, opener=lambda port: fake)
    d = dashboard.Dashboard(root, backend=b)
    d.port = "COM99"                     # never look for the real plotter
    if not save:
        d.save_setting = lambda **v: d.config.update(v)   # keep the real file
    return root, d


def pump(root, until, seconds=10):
    end = time.time() + seconds
    while time.time() < end and not until():
        root.update()
        time.sleep(0.02)


class TestDashboard(unittest.TestCase):

    def test_starts_with_plot_disabled(self):
        root, d = make(FakeGrbl())
        try:
            self.assertEqual(str(d.btn_plot["state"]), "disabled")
            self.assertIn("Connect", d.status["text"])
        finally:
            root.destroy()

    def test_connect_origin_open_and_plot(self):
        fake = FakeGrbl()
        root, d = make(fake)
        try:
            d.check.pen_setup_done = "2026-10-04"
            d.on_connect()
            self.assertTrue(d.check.connected)
            d.backend.set_origin()
            d.check.origin_set = True
            d.load_file(os.path.join(SAMPLES, "square.py"))
            self.assertEqual(str(d.btn_plot["state"]), "normal")
            d.on_plot()
            pump(root, lambda: not d.plotting)
            self.assertFalse(d.plotting)
            self.assertIn("G1 X25.000 Y0.000 F1500", fake.sent)
        finally:
            root.destroy()

    def test_too_big_drawing_blocks_plot_until_fit(self):
        root, d = make(FakeGrbl())
        try:
            d.check.pen_setup_done = "x"
            d.on_connect()
            d.backend.set_origin()
            d.check.origin_set = True
            d.load_file(os.path.join(SAMPLES, "square.py"))
            d.scale.set(1000)
            d.refresh()
            self.assertEqual(str(d.btn_plot["state"]), "disabled")
            d.on_fit()
            self.assertEqual(str(d.btn_plot["state"]), "normal")
        finally:
            root.destroy()


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python tests/test_dashboard_smoke.py`
Expected: `ModuleNotFoundError: No module named 'dashboard'`

- [ ] **Step 3: Write the window**

Create `dashboard.py`:

```python
"""
dashboard.py  -  the teacher's control window for the AX4 pen plotter.

    python dashboard.py        (or open it in Thonny and press Run)

Open a student's emailed turtle program, check the preview, and plot it.
First-time setup: docs/SETUP.md.
"""

import datetime
import os
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import dashboard_logic as logic
from grbl_backend import GrblBackend, LETTER_MM, PlotStopped, usable_half
from plotter import PlotterError, load_config, save_config

PX_PER_MM = 2.0
JOG_STEPS = (1, 10)


class Dashboard:

    def __init__(self, root, backend=None):
        self.root = root
        root.title("AX4 Plotter")
        self.raw_config = load_config()
        self.config = logic.ax4_config(self.raw_config)
        self.half = usable_half(margin=float(self.config["margin_mm"]))
        self.backend = backend or GrblBackend(self.config)
        self.port = None             # None = find the CH340 automatically
        self.check = logic.Checklist(self.config)
        self.strokes = []            # turtle units from the student file
        self.result = None
        self.path = None
        self.plotting = False
        self.paused = False
        self._on_done = None
        self.events = queue.Queue()
        self._build()
        self.refresh()
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        root.after(100, self._poll)

    # ---- layout ---------------------------------------------------------

    def _build(self):
        r = self.root
        top = ttk.Frame(r, padding=6)
        top.grid(row=0, column=0, columnspan=3, sticky="ew")
        self.check_labels = {}
        for i, key in enumerate(("connected", "pen", "origin", "calibrated")):
            lab = ttk.Label(top, width=30)
            lab.grid(row=0, column=i, padx=4, sticky="w")
            self.check_labels[key] = lab
        self.banner = tk.Label(top, bg="#ffe066", fg="black", anchor="w")
        self.banner.grid(row=1, column=0, columnspan=4, sticky="ew", pady=(4, 0))
        self.status = ttk.Label(top, anchor="w")
        self.status.grid(row=2, column=0, columnspan=4, sticky="ew", pady=(4, 0))

        left = ttk.Frame(r, padding=6)
        left.grid(row=1, column=0, sticky="ns")
        self.btn_connect = ttk.Button(left, text="Connect", command=self.on_connect)
        self.btn_connect.pack(fill="x")
        ttk.Label(left, text="Move head (pen up)").pack(pady=(12, 0))
        self.jog_step = tk.IntVar(value=10)
        steps = ttk.Frame(left)
        steps.pack()
        for s in JOG_STEPS:
            ttk.Radiobutton(steps, text="%d mm" % s, value=s,
                            variable=self.jog_step).pack(side="left")
        pad = ttk.Frame(left)
        pad.pack()
        self.jog_buttons = []
        for text, dx, dy, row, col in (("Up", 0, 1, 0, 1), ("Left", -1, 0, 1, 0),
                                       ("Right", 1, 0, 1, 2), ("Down", 0, -1, 2, 1)):
            b = ttk.Button(pad, text=text, width=6,
                           command=lambda dx=dx, dy=dy: self.on_jog(dx, dy))
            b.grid(row=row, column=col)
            self.jog_buttons.append(b)
        self.btn_origin = ttk.Button(left, text="Set origin here",
                                     command=self.on_set_origin)
        self.btn_pen_up = ttk.Button(left, text="Pen up",
                                     command=lambda: self.on_pen(False))
        self.btn_pen_down = ttk.Button(left, text="Pen down",
                                       command=lambda: self.on_pen(True))
        self.btn_change = ttk.Button(left, text="Change pen",
                                     command=self.on_change_pen)
        self.btn_pen_setup = ttk.Button(left, text="Pen setup...",
                                        command=self.on_pen_setup)
        self.btn_calibrate = ttk.Button(left, text="Calibrate distances...",
                                        command=self.on_calibrate)
        for b in (self.btn_origin, self.btn_pen_up, self.btn_pen_down,
                  self.btn_change, self.btn_pen_setup, self.btn_calibrate):
            b.pack(fill="x", pady=(8, 0))

        w = int(LETTER_MM[0] * PX_PER_MM) + 20
        h = int(LETTER_MM[1] * PX_PER_MM) + 20
        self.canvas = tk.Canvas(r, width=w, height=h, bg="#ddd",
                                highlightthickness=0)
        self.canvas.grid(row=1, column=1, padx=6, pady=6)

        right = ttk.Frame(r, padding=6)
        right.grid(row=1, column=2, sticky="ns")
        self.file_label = ttk.Label(right, text="No student file open",
                                    font=("TkDefaultFont", 10, "bold"))
        self.file_label.pack(anchor="w")
        self.info = ttk.Label(right, justify="left", wraplength=340)
        self.info.pack(anchor="w", pady=4)
        self.code = tk.Text(right, width=50, height=24, font=("Courier", 9),
                            state="disabled")
        self.code.pack(fill="both", expand=True)

        bottom = ttk.Frame(r, padding=6)
        bottom.grid(row=2, column=0, columnspan=3, sticky="ew")
        ttk.Button(bottom, text="Open student file...",
                   command=self.on_open).pack(side="left")
        ttk.Label(bottom, text="   Scale %").pack(side="left")
        self.scale = tk.IntVar(value=100)
        sb = ttk.Spinbox(bottom, from_=1, to=logic.MAX_SCALE, width=5,
                         textvariable=self.scale, command=self.refresh)
        sb.pack(side="left")
        sb.bind("<Return>", lambda e: self.refresh())
        sb.bind("<FocusOut>", lambda e: self.refresh())
        ttk.Button(bottom, text="Fit to paper",
                   command=self.on_fit).pack(side="left", padx=2)
        ttk.Button(bottom, text="Reset 100%",
                   command=self.on_reset_scale).pack(side="left")
        self.btn_plot = ttk.Button(bottom, text="Plot", command=self.on_plot)
        self.btn_pause = ttk.Button(bottom, text="Pause", command=self.on_pause)
        self.btn_stop = tk.Button(bottom, text="STOP", bg="#d33", fg="white",
                                  font=("TkDefaultFont", 10, "bold"),
                                  command=self.on_stop)
        self.btn_svg = ttk.Button(bottom, text="Save SVG...",
                                  command=self.on_save_svg)
        for b in (self.btn_plot, self.btn_pause, self.btn_stop, self.btn_svg):
            b.pack(side="left", padx=4)
        self.progress = ttk.Progressbar(bottom, length=220)
        self.progress.pack(side="left", padx=8)

    # ---- state ----------------------------------------------------------

    def _scale(self):
        try:
            v = int(self.scale.get())
        except (tk.TclError, ValueError):
            v = 100
        return max(1, min(logic.MAX_SCALE, v))

    def strokes_mm(self):
        return logic.to_mm(self.strokes, self._scale())

    def _sync_from_backend(self):
        self.check.connected = self.backend.connected
        self.check.origin_set = self.backend.origin_set

    def refresh(self):
        c = self.check
        tick = lambda ok: "[x] " if ok else "[ ] "
        self.check_labels["connected"].config(text=tick(c.connected) + "Connected to AX4")
        self.check_labels["pen"].config(text=tick(c.pen_setup_done) + "Pen set up")
        self.check_labels["origin"].config(text=tick(c.origin_set) + "Origin set")
        self.check_labels["calibrated"].config(
            text=tick(c.calibrated) + ("Calibrated %s" % c.calibrated
                                       if c.calibrated else "Distances calibrated"))
        if c.banner:
            self.banner.config(text=c.banner)
            self.banner.grid()
        else:
            self.banner.grid_remove()

        mm = self.strokes_mm()
        blocker = logic.plot_blocker(c, mm, self.half)
        idle = not self.plotting
        ready = c.connected and idle
        self.btn_connect.config(text="Disconnect" if c.connected else "Connect",
                                state="normal" if idle else "disabled")
        for b in self.jog_buttons + [self.btn_origin, self.btn_pen_up,
                                     self.btn_pen_down, self.btn_change,
                                     self.btn_pen_setup, self.btn_calibrate]:
            b.config(state="normal" if ready else "disabled")
        self.btn_plot.config(state="normal" if idle and blocker is None else "disabled")
        self.btn_pause.config(state="normal" if self.plotting else "disabled",
                              text="Resume" if self.paused else "Pause")
        self.btn_svg.config(state="normal" if mm and idle else "disabled")
        if idle:
            self.status.config(text=blocker or "Ready to plot.")
        self._draw_preview(mm)
        self._show_info(mm)

    def _draw_preview(self, mm):
        cv = self.canvas
        cv.delete("all")
        k = PX_PER_MM
        ox = 10 + LETTER_MM[0] * k / 2
        oy = 10 + LETTER_MM[1] * k / 2

        def px(x, y):
            return ox + x * k, oy - y * k

        cv.create_rectangle(*px(-LETTER_MM[0] / 2, LETTER_MM[1] / 2),
                            *px(LETTER_MM[0] / 2, -LETTER_MM[1] / 2),
                            fill="white", outline="#999")
        hx, hy = self.half
        cv.create_rectangle(*px(-hx, hy), *px(hx, -hy), outline="#9bd",
                            dash=(4, 3))
        cv.create_line(*px(-4, 0), *px(4, 0), fill="#c33")
        cv.create_line(*px(0, -4), *px(0, 4), fill="#c33")
        greyed = bool(self.result and self.result.get("error"))
        for s in mm:
            for a, b in zip(s, s[1:]):
                bad = not (logic.inside(a, self.half) and logic.inside(b, self.half))
                colour = "red" if bad else ("#999" if greyed else "black")
                cv.create_line(*px(*a), *px(*b), fill=colour,
                               width=2 if bad else 1)

    def _show_info(self, mm):
        if self.result is None:
            self.info.config(text="")
            return
        w, h = logic.size_mm(mm)
        secs = logic.estimate_seconds(mm, self.config["draw_feed"],
                                      self.config["travel_feed"],
                                      self.config["servo_wait_s"])
        lines = ["%d strokes, %.0f x %.0f mm at %d%%" % (len(mm), w, h, self._scale()),
                 "Estimated time: %s" % logic.format_time(secs)]
        lines += ["Warning: " + x for x in self.result.get("warnings", [])]
        err = logic.error_text(self.result.get("error"))
        if err:
            lines.append("ERROR: " + err)
        self.info.config(text="\n".join(lines))

    # ---- helpers used by the wizards ----------------------------------

    def save_setting(self, **values):
        self.raw_config.update(values)
        self.config.update(values)
        save_config(self.raw_config)

    def mark_pen_setup(self):
        today = datetime.date.today().isoformat()
        self.save_setting(pen_setup_done=today)
        self.check.pen_setup_done = today
        self.refresh()

    def mark_calibrated(self):
        today = datetime.date.today().isoformat()
        self.save_setting(calibrated=today)
        self.check.calibrated = today
        self.refresh()

    def _try(self, action, *args):
        """Run a backend action from a button; show problems in a dialog."""
        try:
            action(*args)
        except PlotterError as e:
            messagebox.showerror("Plotter", str(e), parent=self.root)
        self._sync_from_backend()
        self.refresh()

    # ---- buttons --------------------------------------------------------

    def on_connect(self):
        if self.check.connected:
            self.backend.close()
            self._sync_from_backend()
            self.refresh()
            return
        self.status.config(text="Connecting...")
        self.root.update_idletasks()
        self._try(self.backend.connect, self.port)

    def on_jog(self, dx, dy):
        step = self.jog_step.get()
        self._try(self.backend.jog, dx * step, dy * step)

    def on_set_origin(self):
        if messagebox.askokcancel(
                "Set origin",
                "Is the sheet centred on the plotter bed, and the pen over "
                "the centre of the sheet?", parent=self.root):
            self._try(self.backend.set_origin)

    def on_pen(self, down):
        self._try(self.backend.pen, down)

    def on_change_pen(self):
        if not self.backend.origin_set:
            messagebox.showinfo("Change pen", "Set the origin first, so the "
                                "head knows where the sheet is.", parent=self.root)
            return
        feed = self.config["travel_feed"]

        def go():
            self.backend.pen(False)
            self.backend.move(0.0, -self.half[1], feed)
            self.backend.wait()
            messagebox.showinfo("Change pen", "Swap the pen, then click OK.\n"
                                "The head will go back to the centre.",
                                parent=self.root)
            self.backend.move(0.0, 0.0, feed)
            self.backend.wait()
        self._try(go)

    def on_pen_setup(self):
        from dashboard_wizards import PenSetupWizard
        PenSetupWizard(self)

    def on_calibrate(self):
        from dashboard_wizards import CalibrationWizard
        CalibrationWizard(self)

    def on_open(self):
        path = filedialog.askopenfilename(
            parent=self.root, title="Open a student's turtle program",
            filetypes=[("Python files", "*.py"), ("All files", "*.*")])
        if path:
            self.load_file(path)

    def load_file(self, path):
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                source = f.read()
        except OSError as e:
            messagebox.showerror("Open", str(e), parent=self.root)
            return
        self.path = path
        self.file_label.config(text=os.path.basename(path))
        self.code.config(state="normal")
        self.code.delete("1.0", "end")
        self.code.insert("1.0", source)
        self.code.config(state="disabled")
        self.status.config(text="Running the student's program...")
        self.root.config(cursor="watch")
        self.root.update_idletasks()
        try:
            self.result = logic.run_student(path)
        finally:
            self.root.config(cursor="")
        self.strokes = self.result.get("strokes", [])
        self.scale.set(100)
        self.refresh()

    def on_fit(self):
        self.scale.set(logic.fit_scale(self.strokes, self.half))
        self.refresh()

    def on_reset_scale(self):
        self.scale.set(100)
        self.refresh()

    def on_plot(self):
        mm = self.strokes_mm()
        if logic.plot_blocker(self.check, mm, self.half):
            return
        name = os.path.basename(self.path) if self.path else "drawing"
        self.start_job(mm, "Plotting " + name)

    def start_job(self, strokes_mm, label, on_done=None):
        """Plot in a worker thread; results come back through self.events."""
        self.plotting = True
        self.paused = False
        self._on_done = on_done
        self.progress.config(maximum=max(1, len(strokes_mm)), value=0)
        self.status.config(text=label + "...")

        def work():
            try:
                logic.plot_strokes(
                    self.backend, strokes_mm, self.config["draw_feed"],
                    self.config["travel_feed"],
                    progress=lambda i, n: self.events.put(("progress", i, n)))
                self.events.put(("done",))
            except PlotStopped:
                try:
                    self.backend.recover()
                    self.events.put(("stopped",))
                except PlotterError as e:
                    self.events.put(("error", e))
            except PlotterError as e:
                self.events.put(("error", e))

        threading.Thread(target=work, daemon=True).start()
        self.refresh()

    def _poll(self):
        try:
            while True:
                ev = self.events.get_nowait()
                if ev[0] == "progress":
                    self.progress.config(value=ev[1])
                    self.status.config(text="Stroke %d of %d" % (ev[1], ev[2]))
                    continue
                self.plotting = False
                self.paused = False
                self._sync_from_backend()
                callback, self._on_done = self._on_done, None
                self.refresh()
                if ev[0] == "done":
                    self.status.config(text="Finished.")
                    if callback:
                        callback()
                elif ev[0] == "stopped":
                    messagebox.showinfo(
                        "Stopped", "Plot stopped.  The pen is up.\nSet the "
                        "origin again before the next plot.", parent=self.root)
                else:
                    messagebox.showerror("Plotter", str(ev[1]), parent=self.root)
        except queue.Empty:
            pass
        self.root.after(100, self._poll)

    def on_pause(self):
        if not self.plotting:
            return
        try:
            if self.paused:
                self.backend.resume()
            else:
                self.backend.pause()
            self.paused = not self.paused
        except PlotterError as e:
            messagebox.showerror("Plotter", str(e), parent=self.root)
        self.refresh()

    def on_stop(self):
        if not self.backend.connected:
            return
        try:
            self.backend.stop()
            if not self.plotting:
                self.backend.recover()
        except PlotterError as e:
            messagebox.showerror("Plotter", str(e), parent=self.root)
        self.paused = False
        self._sync_from_backend()
        self.refresh()

    def on_save_svg(self):
        base = os.path.splitext(os.path.basename(self.path or "drawing"))[0]
        path = filedialog.asksaveasfilename(
            parent=self.root, defaultextension=".svg",
            initialfile=base + ".svg", filetypes=[("SVG drawing", "*.svg")])
        if not path:
            return
        with open(path, "w", encoding="utf-8") as f:
            f.write(logic.svg_text(self.strokes_mm()))
        self.status.config(text="Saved " + path)

    def on_close(self):
        if self.plotting:
            if not messagebox.askyesno("Quit", "A plot is running.  Stop the "
                                       "plot and quit?", parent=self.root):
                return
            try:
                self.backend.stop()
            except PlotterError:
                pass
        elif self.backend.connected:
            try:
                self.backend.pen(False)
            except PlotterError:
                pass
        self.backend.close()
        self.root.destroy()


def main():
    root = tk.Tk()
    Dashboard(root)
    root.mainloop()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the smoke tests**

Run: `python tests/test_dashboard_smoke.py`
Expected: `Ran 3 tests ... OK`

- [ ] **Step 5: Look at it (no plotter needed)**

Run: `python dashboard.py`
Check by eye: the checklist row, the yellow NOT CALIBRATED banner, the Letter sheet with a dashed usable area and a red cross at the centre, Plot disabled with "Connect to the plotter." in the status line. Open `tests/samples/square.py`: code on the right, a square in the preview, "1 strokes, 25 x 25 mm at 100%". Set scale to 1000: the square turns red and Plot stays disabled. Fit to paper: black again. Close the window.

- [ ] **Step 6: Checkpoint**

Run: `for f in tests/test_*.py; do python "$f" || break; done`
Expected: all OK.

---

### Task 6: Pen setup and calibration wizards

**Files:**
- Create: `dashboard_wizards.py`
- Modify: `tests/test_dashboard_smoke.py` (add wizard tests)

**Interfaces:**
- Consumes: `Dashboard.backend`, `.check`, `.refresh()`, `.start_job(strokes_mm, label, on_done)`, `.save_setting(**values)`, `.mark_pen_setup()`, `.mark_calibrated()` (Task 5); `zigzag_strokes`, `calibration_strokes`, `calibration_result` (Task 4); `GrblBackend.servo/pen/read_settings/write_setting/origin_set/pen_touch_s/pen_down_s` (Task 1).
- Produces: `class PenSetupWizard(dash)`, `class CalibrationWizard(dash)` (both `tk.Toplevel`), each with step methods named below.

- [ ] **Step 1: Add the failing wizard tests**

Append to `tests/test_dashboard_smoke.py`, above the `if __name__` line:

```python
class TestWizards(unittest.TestCase):

    def test_pen_setup_lifts_then_goes_to_touch_position(self):
        fake = FakeGrbl()
        root, d = make(fake)
        try:
            d.on_connect()
            fake.sent.clear()
            import dashboard_wizards
            w = dashboard_wizards.PenSetupWizard(d)
            self.assertIn("M5", fake.sent)
            w.s2()
            w.s3()
            self.assertIn("M3 S60", fake.sent)
            w.destroy()
        finally:
            root.destroy()

    def test_pen_setup_test_needs_an_origin(self):
        root, d = make(FakeGrbl())
        try:
            d.on_connect()
            import dashboard_wizards
            w = dashboard_wizards.PenSetupWizard(d)
            w.s4()
            self.assertIn("Set origin here", w.text["text"])
            w.destroy()
        finally:
            root.destroy()

    def test_pen_setup_solid_lines_ticks_the_checklist(self):
        root, d = make(FakeGrbl())
        try:
            d.on_connect()
            d.check.pen_setup_done = None
            import dashboard_wizards
            w = dashboard_wizards.PenSetupWizard(d)
            w.done()
            self.assertTrue(d.check.pen_setup_done)
            w.destroy()
        finally:
            root.destroy()

    def test_calibration_applies_the_average_to_both_axes(self):
        fake = FakeGrbl(replies={"$$": ["$100=80.000 (x, step/mm)",
                                        "$101=80.000 (y, step/mm)", "ok"]})
        root, d = make(fake)
        try:
            d.on_connect()
            d.backend.set_origin()
            d.check.origin_set = True
            d.check.pen_setup_done = "x"
            import dashboard_wizards
            w = dashboard_wizards.CalibrationWizard(d)
            w.s2()
            w.vx.set("149")
            w.vy.set("149")
            w.calc()
            fake.sent.clear()
            w.apply()
            self.assertEqual(fake.sent, ["$100=80.537", "$101=80.537"])
            self.assertTrue(d.check.calibrated)
            self.assertFalse(d.backend.origin_set)
            w.destroy()
        finally:
            root.destroy()
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python tests/test_dashboard_smoke.py`
Expected: the 4 new tests ERROR with `ModuleNotFoundError: No module named 'dashboard_wizards'`; the 3 older ones still pass.

- [ ] **Step 3: Write the wizards**

Create `dashboard_wizards.py`:

```python
"""
dashboard_wizards.py  -  step-by-step Pen setup and Calibrate distances.

Written for someone doing this for the first time, maybe years from now.
Each step is one screen with plain instructions and one or two buttons.
"""

import tkinter as tk
from tkinter import messagebox, ttk

import dashboard_logic as logic
from plotter import PlotterError


class Wizard(tk.Toplevel):
    """A small window that shows one step at a time."""

    def __init__(self, dash, title):
        super().__init__(dash.root)
        self.dash = dash
        self.b = dash.backend
        self.title(title)
        self.transient(dash.root)
        self.text = ttk.Label(self, wraplength=440, justify="left", padding=12)
        self.text.pack(fill="x")
        self.extra = ttk.Frame(self, padding=(12, 0))
        self.extra.pack(fill="x")
        self.buttons = ttk.Frame(self, padding=12)
        self.buttons.pack(fill="x")

    def step(self, text, buttons):
        """Show `text` and a row of (label, callback) buttons."""
        self.text.config(text=text)
        for w in self.extra.winfo_children() + self.buttons.winfo_children():
            w.destroy()
        for label, callback in buttons:
            ttk.Button(self.buttons, text=label,
                       command=callback).pack(side="left", padx=4)

    def act(self, fn, *args):
        """Run a plotter action; on a problem show it and return False."""
        try:
            fn(*args)
            return True
        except PlotterError as e:
            messagebox.showerror("Plotter", str(e), parent=self)
            self.dash._sync_from_backend()
            self.dash.refresh()
            return False


class PenSetupWizard(Wizard):

    def __init__(self, dash):
        super().__init__(dash, "Pen setup")
        self.s1()

    def s1(self):
        if not self.act(self.b.servo, None):
            return
        self.step("Step 1 of 4\n\n"
                  "The pen holder is now lifted.\n"
                  "Loosen the pen clamp and take the pen out.",
                  [("Next", self.s2), ("Pen is already set - skip to test",
                                       self.s4)])

    def s2(self):
        self.step("Step 2 of 4\n\n"
                  "Put a sheet of paper under the pen holder.\n"
                  "Then click 'Lower to touch position'.",
                  [("Lower to touch position", self.s3)])

    def s3(self):
        if not self.act(self.b.servo, self.b.pen_touch_s):
            return
        self.step("Step 3 of 4\n\n"
                  "Slide the pen down into the clamp until the tip just "
                  "touches the paper, then tighten the clamp.\n\n"
                  "The pen should rest on the paper - not on the bottom of "
                  "its holder.  It needs a little room to move down so it "
                  "can follow bumps in the paper.",
                  [("Next", self.s4)])
        self._advanced()

    def s4(self):
        if not self.act(self.b.servo, None):
            return
        if not self.b.origin_set:
            self.step("Step 4 of 4 - test\n\n"
                      "The test draws in the middle of the sheet, so the "
                      "plotter needs to know where the middle is.\n\n"
                      "Close this window.  Use the arrow buttons to move the "
                      "head over the centre of the sheet and click "
                      "'Set origin here'.  Then open Pen setup again and "
                      "choose 'skip to test'.",
                      [("Close", self.destroy)])
            return
        self.step("Step 4 of 4 - test\n\n"
                  "The plotter will draw three small zigzags in the middle "
                  "of the sheet.",
                  [("Draw test", self.s4_draw)])

    def s4_draw(self):
        self.step("Drawing the test...", [])
        self.dash.start_job(logic.zigzag_strokes(), "Pen test",
                            on_done=self.s5)

    def s5(self):
        self.step("What do you see on the paper?",
                  [("Solid lines", self.done),
                   ("Faint, gaps or nothing", self.too_high),
                   ("Lines joining the zigzags", self.not_lifting)])

    def too_high(self):
        self.step("The pen isn't pressing on the paper.\n\n"
                  "Click 'Lower to touch position', loosen the clamp, slide "
                  "the pen about 1 mm further down, tighten, then test "
                  "again.",
                  [("Lower to touch position", self.s3)])

    def not_lifting(self):
        self.step("The pen isn't lifting between lines.\n\n"
                  "Check that the servo arm (the small white horn) pushes "
                  "the pen holder up when the pen is up.  If the horn has "
                  "slipped, take out its screw, refit it so it lifts the "
                  "holder, and run Pen setup again.",
                  [("Close", self.destroy)])

    def done(self):
        self.dash.mark_pen_setup()
        self.step("Pen setup is done.", [("Close", self.destroy)])

    def _advanced(self):
        box = ttk.LabelFrame(self.extra, text="Advanced - only if a different "
                             "pen or servo needs other numbers")
        box.pack(fill="x", pady=6)
        for label, attr in (("Touch position (S)", "pen_touch_s"),
                            ("Pen down (S)", "pen_down_s")):
            row = ttk.Frame(box)
            row.pack(fill="x")
            ttk.Label(row, text=label, width=18).pack(side="left")
            var = tk.IntVar(value=getattr(self.b, attr))
            scale = tk.Scale(row, from_=0, to=150, orient="horizontal",
                             variable=var, length=240)
            scale.pack(side="left")

            def changed(_event, var=var, attr=attr):
                value = int(var.get())
                setattr(self.b, attr, value)
                self.act(self.b.servo, value)
                self.dash.save_setting(**{attr: value})
            scale.bind("<ButtonRelease-1>", changed)


class CalibrationWizard(Wizard):

    def __init__(self, dash):
        super().__init__(dash, "Calibrate distances")
        self.new = None
        if not (dash.check.pen_setup_done and self.b.origin_set):
            self.step("Before calibrating: run Pen setup, put down a fresh "
                      "sheet centred on the bed, move the head over its "
                      "centre and click 'Set origin here'.",
                      [("Close", self.destroy)])
            return
        self.s1()

    def s1(self):
        self.step("Step 1 of 3\n\n"
                  "The plotter will draw an L: a 150 mm line across and a "
                  "150 mm line up, with a short tick at the far end of each.",
                  [("Draw the L", self.draw)])

    def draw(self):
        self.step("Drawing...", [])
        self.dash.start_job(logic.calibration_strokes(), "Calibration L",
                            on_done=self.s2)

    def s2(self):
        self.step("Step 2 of 3\n\n"
                  "With a ruler, measure each line from the corner of the L "
                  "to the middle of its tick.  Type the lengths in "
                  "millimetres.",
                  [("Calculate", self.calc)])
        self.vx, self.vy = tk.StringVar(), tk.StringVar()
        for label, var in (("Line across (X), mm", self.vx),
                           ("Line up (Y), mm", self.vy)):
            row = ttk.Frame(self.extra)
            row.pack(fill="x", pady=2)
            ttk.Label(row, text=label, width=22).pack(side="left")
            ttk.Entry(row, textvariable=var, width=8).pack(side="left")

    def calc(self):
        try:
            mx, my = float(self.vx.get()), float(self.vy.get())
        except ValueError:
            messagebox.showerror("Calibrate", "Please type two numbers, "
                                 "like 149.5", parent=self)
            return
        settings = {}
        if not self.act(lambda: settings.update(self.b.read_settings())):
            return
        current = settings.get(100, 80.0)
        try:
            self.new, differ = logic.calibration_result(current, mx, my)
        except ValueError as e:
            messagebox.showerror("Calibrate", str(e), parent=self)
            return
        note = ("\n\nX and Y came out more than 1% different.  This plotter "
                "moves both directions with the same two motors, so one "
                "number is used for both (the average)." if differ else "")
        self.step("Step 3 of 3\n\n"
                  "Steps per mm: %.3f  ->  %.3f%s\n\n"
                  "Click Apply to store this in the plotter."
                  % (current, self.new, note),
                  [("Apply", self.apply), ("Cancel", self.destroy)])

    def apply(self):
        if not self.act(self.b.write_setting, 100, self.new):
            return
        if not self.act(self.b.write_setting, 101, self.new):
            return
        # The plotter's sense of distance just changed: the old origin
        # no longer means the same place.
        self.b.origin_set = False
        self.dash.check.origin_set = False
        self.dash.mark_calibrated()
        self.step("Saved.\n\n"
                  "Set the origin again before the next plot.  To check, "
                  "put down a fresh sheet, set the origin, and run "
                  "Calibrate distances again: both lines should now "
                  "measure 150 mm.",
                  [("Close", self.destroy)])
```

- [ ] **Step 4: Run the smoke tests**

Run: `python tests/test_dashboard_smoke.py`
Expected: `Ran 7 tests ... OK`

- [ ] **Step 5: Checkpoint**

Run: `for f in tests/test_*.py; do python "$f" || break; done`
Expected: all OK.

---

### Task 7: Teacher docs, notes, and hardware acceptance

**Files:**
- Modify: `docs/SETUP.md` (append an AX4 section)
- Modify: `docs/HARDWARE_NOTES.md` (append results)
- Modify: `SESSION_NOTES.md`

**Interfaces:**
- Consumes: the finished dashboard.
- Produces: written instructions a future teacher can follow; recorded answers to the spec's three open hardware questions.

- [ ] **Step 1: Append the AX4 section to `docs/SETUP.md`**

```markdown
## AX4 dashboard (teacher)

Start: open `dashboard.py` in Thonny and press Run (or double-click it).
If Candle is open, click Disconnect in Candle first - only one program can
use the plotter at a time.

Every session:
1. Click **Connect**.
2. Put a Letter sheet on the bed, landscape, **centred on the bed** (the
   plotter only travels 210 mm front to back; the sheet is 216 mm).
3. Use the arrow buttons to move the pen over the centre of the sheet.
   Click **Set origin here**.
4. **Open student file...**, check the preview and messages, adjust
   **Scale %** or click **Fit to paper**, then **Plot**.
5. **STOP** lifts the pen and stops at once. Set the origin again after it.

Once, and whenever the pen changes: **Pen setup...** (four guided steps).

Once, and if drawings measure wrong: **Calibrate distances...** (draws an
L, you measure it with a ruler). The yellow NOT CALIBRATED bar stays until
this is done.

Students: write normal turtle programs (`import turtle`) and email the .py
file. They do not need plotter.py. `input()`, colours, fills and text are
not plotted; the dashboard says so.

Manual check after changing dashboard code:
- [ ] Opens with Plot disabled and the checklist unticked except Pen set up.
- [ ] Open tests/samples/square.py: preview shows a square, info shows
      25 x 25 mm at 100%.
- [ ] Scale 1000: drawing turns red, Plot disabled. Fit to paper: black.
- [ ] Open tests/samples/typo.py: ERROR line names line 5; partial drawing
      greyed.
- [ ] Open tests/samples/forever.py: after 20 s, "took too long".
```

- [ ] **Step 2: Hardware stage 1 - connect (teacher present; ask "go" first)**

Teacher at the plotter, hand on the power switch, Candle disconnected.
Run `python dashboard.py`, click Connect. Expected: Connected ticked,
nothing moves.

- [ ] **Step 3: Hardware stage 2 - pen setup (ask "go" first)**

Run Pen setup... through to the zigzag test. Expected: three clean zigzags,
no joining lines. Record the result.

- [ ] **Step 4: Hardware stage 3 - origin and a small plot (ask "go" first)**

Fresh sheet, centred. Jog to centre, Set origin here, open
`tests/samples/square.py`, Plot. Expected: a 25 mm square centred on the
sheet; head returns to centre.

- [ ] **Step 5: Hardware stage 4 - STOP mid-plot (ask "go" first)**

Open `tests/samples/square.py` at 400% (a 100 mm square), Plot, press
STOP after a second. Expected: motion stops at once, pen lifts, "Plot
stopped" dialog, Origin set unticked, Connect still ticked. **Record what
GRBL 0.9 reported after Ctrl-X** (ALARM or Idle) - spec open item 1.

- [ ] **Step 6: Hardware stage 5 - calibration (ask "go" first)**

Run Calibrate distances... Record the two measurements and the old and
new steps/mm shown in step 3. Then set the origin and run it once more on a
fresh sheet: both lines should measure 150 mm. Spec open item 2 (CoreXY,
`$100` vs `$101`) is settled by design: the wizard always writes the
average to both, so no separate test is needed unless the two measurements
disagree by more than 1% - if they do, record it.

- [ ] **Step 7: Record findings**

Append to `docs/HARDWARE_NOTES.md` a dated "AX4 dashboard acceptance"
section with each stage's result, timings, the Ctrl-X behaviour, the
calibration numbers, and whether `G4 P0` before `M3`/`M5` was ever seen to
matter (spec open item 3). Update `SESSION_NOTES.md`: what was built, test
counts, hardware results, what is next. Update the
`ax4-dashboard-direction` project memory if a decision changed.

- [ ] **Step 8: Final checkpoint**

Run: `for f in tests/test_*.py; do python "$f" || break; done`
Expected: all OK. Tell the teacher the files are ready to commit.
