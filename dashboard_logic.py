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

import code_check
from grbl_backend import LETTER_MM

STEP_MM = 0.25               # 100% scale: one turtle step = 0.25 mm
MAX_SCALE = 1000
STUDENT_TIMEOUT = 20         # seconds a student program may run
CAL_MM = 150.0               # length of each calibration line
RUNNER = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                      "run_turtle.py")
UPLOADS = os.path.join(os.path.dirname(RUNNER), "uploads")   # Pi upload page

AX4_DEFAULTS = {
    "backend": "grbl", "paper": "letter", "margin_mm": 10,
    "pen_touch_s": 60, "pen_down_s": 80, "servo_wait_s": 0.3,
    "draw_feed": 1500, "travel_feed": 3000,
    "pen_setup_done": None, "calibrated": None,
    "run_as": None, "stop_pin": None,        # Pi only: see docs/PI_SETUP.md
}

_PLAIN_ERRORS = ("Timeout", "KeyboardInputNotSupported", "RunnerFailed",
                 "NotAllowed", "PhotoError")


def ax4_config(raw):
    """The config file's values on top of AX4_DEFAULTS."""
    cfg = dict(AX4_DEFAULTS)
    cfg.update(raw)
    return cfg


# ---- running student code --------------------------------------------------

def _failed(kind, message):
    return {"strokes": [], "warnings": [],
            "error": {"type": kind, "message": message, "line": None}}


def student_command(path, run_as=None):
    """The command that runs a student file; as another user if run_as."""
    cmd = [sys.executable, RUNNER, path]
    if run_as:
        cmd = ["sudo", "-n", "-u", run_as] + cmd
    return cmd


def _runner_failed(detail, run_as):
    if run_as:
        return ("Couldn't run the program as user %s - see docs/PI_SETUP.md.\n%s"
                % (run_as, detail))
    return detail


def run_student(path, timeout=STUDENT_TIMEOUT, run_as=None):
    """Check a student's .py, then run it in a separate process and return
    what it drew."""
    try:
        with open(path, encoding="utf-8-sig", errors="replace") as f:
            source = f.read()
    except OSError as e:
        return _failed("RunnerFailed", str(e))
    problems = code_check.check(source)
    if problems:
        return _failed("NotAllowed", "\n".join(problems))
    flags = 0x08000000 if sys.platform == "win32" else 0   # no console window
    try:
        out = subprocess.run(student_command(path, run_as),
                             capture_output=True, text=True, encoding="utf-8",
                             errors="replace", timeout=timeout,
                             creationflags=flags)
    except subprocess.TimeoutExpired:
        return _failed("Timeout", "The program took too long - is there a "
                                  "loop that never ends?")
    except OSError as e:                     # e.g. no sudo on this machine
        return _failed("RunnerFailed", _runner_failed(str(e), run_as))
    try:
        return json.loads(out.stdout)
    except ValueError:
        last = (out.stderr.strip().splitlines() or
                ["The program could not be run."])[-1]
        return _failed("RunnerFailed", _runner_failed(last, run_as))


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


def stroke_estimates(strokes_mm, draw_feed, travel_feed, pen_s=0.3,
                     per_seg=0.05):
    """Seconds for each stroke: travel to it, draw it, lift.  The trip back
    to the origin at the end is added to the last one."""
    out = []
    pos = (0.0, 0.0)
    for s in strokes_mm:
        t = math.dist(pos, s[0]) / (travel_feed / 60.0)
        for a, b in zip(s, s[1:]):
            t += math.dist(a, b) / (draw_feed / 60.0) + per_seg
        out.append(t + 2 * pen_s)
        pos = s[-1]
    if out:
        out[-1] += math.dist(pos, (0.0, 0.0)) / (travel_feed / 60.0)
    return out


def estimate_seconds(strokes_mm, draw_feed, travel_feed, pen_s=0.3,
                     per_seg=0.05):
    return sum(stroke_estimates(strokes_mm, draw_feed, travel_feed, pen_s,
                                per_seg))


def remaining_seconds(per_stroke, done, elapsed_active):
    """Time left, corrected by how fast the finished strokes really went."""
    left = sum(per_stroke[done:])
    spent_estimate = sum(per_stroke[:done])
    if done and spent_estimate > 0 and elapsed_active > 0:
        left *= elapsed_active / spent_estimate
    return left


def format_clock(seconds):
    s = int(round(seconds))
    return "%d:%02d" % (s // 60, s % 60)


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


# ---- typed text ------------------------------------------------------------

def text_strokes(text):
    """Typed text in write_name.py's single-stroke font, centred on 0,0.

    Returns (strokes in turtle units, sorted list of characters the font
    doesn't have).  If any are missing, strokes is empty.  At 100% the
    capitals are 15 mm tall, the same as write_name.py.
    """
    from write_name import GAP, GLYPHS, UNIT
    missing = sorted({ch for ch in text if ch not in GLYPHS})
    if missing:
        return [], missing
    strokes, x = [], 0.0
    for ch in text:
        width, glyph = GLYPHS[ch]
        for s in glyph:
            strokes.append([((x + px) * UNIT, py * UNIT) for px, py in s])
        x += width + GAP
    if not strokes:
        return [], []
    xs = [p[0] for s in strokes for p in s]
    ys = [p[1] for s in strokes for p in s]
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    return [[((px - cx) / STEP_MM, (py - cy) / STEP_MM) for px, py in s]
            for s in strokes], []


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
