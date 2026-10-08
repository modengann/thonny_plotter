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

# On the Pi the program runs under sudo, and the dashboard's time limit
# can only kill sudo - so the runner also limits itself (Linux/Mac only).
LIMIT_SECONDS = 25                   # a bit longer than the dashboard waits
LIMIT_MEMORY = 1024 * 1024 * 1024

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


def limit_resources():
    """End this process after LIMIT_SECONDS and cap its memory.  Does
    nothing on Windows."""
    try:
        import resource
        import signal
    except ImportError:
        return
    signal.alarm(LIMIT_SECONDS)          # default action: end the process
    resource.setrlimit(resource.RLIMIT_CPU, (LIMIT_SECONDS, LIMIT_SECONDS))
    resource.setrlimit(resource.RLIMIT_AS, (LIMIT_MEMORY, LIMIT_MEMORY))


def main(argv):
    limit_resources()
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
