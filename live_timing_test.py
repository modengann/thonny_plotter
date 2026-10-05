"""
live_timing_test.py  -  teacher tool.  Times a live run, command by command.

Runs hello_shapes.py's drawing against the real printer and reports where the
time actually goes: connect, home, pen lifts, travel, drawing.

*** THIS MOVES THE PRINTER. *** It sends G28.  Pen removed or retracted.

    python live_timing_test.py           # explains itself, moves nothing
    python live_timing_test.py --yes     # actually runs
"""

import sys
import time
import turtle

import plotter
from plotter import Plotter, PlotterError

log = []          # (command, seconds)


def instrument(p):
    """Wrap _send so every command is timed, without touching plotter.py."""
    original = p._send

    def timed(line, timeout=30, collect=False):
        t0 = time.time()
        result = original(line, timeout=timeout, collect=collect)
        log.append((line, time.time() - t0))
        return result

    p._send = timed


def drawing(t):
    """Exactly what hello_shapes.py draws."""
    def square(size):
        for i in range(4):
            t.forward(size)
            t.left(90)

    def move_to(x, y):
        t.penup()
        t.goto(x, y)
        t.pendown()

    x = -260
    for size in [40, 60, 80, 100]:
        move_to(x, -100)
        square(size)
        x = x + size + 20
    t.penup()


def report():
    def total(pred):
        return sum(s for c, s in log if pred(c))

    print("\n%-34s %8s %8s" % ("phase", "count", "seconds"))
    print("-" * 52)
    rows = [
        ("G28 home",        lambda c: c.startswith("G28")),
        ("G1 Z (pen up/down)", lambda c: c.startswith("G1 Z")),
        ("G1 XY drawing (F1500)", lambda c: c.startswith("G1 X") and "F1500" in c),
        ("G1 XY travel (F3000)", lambda c: c.startswith("G1 X") and "F3000" in c),
        ("M400 waits",      lambda c: c.startswith("M400")),
        ("setup (M1xx, G2x)", lambda c: c[:1] == "M" and not c.startswith("M400")),
    ]
    for name, pred in rows:
        n = sum(1 for c, s in log if pred(c))
        print("%-34s %8d %8.2f" % (name, n, total(pred)))
    print("-" * 52)
    print("%-34s %8d %8.2f" % ("ALL COMMANDS", len(log), sum(s for _, s in log)))

    slow = sorted(log, key=lambda r: -r[1])[:8]
    print("\nSlowest individual commands:")
    for c, s in slow:
        print("  %7.2fs  %s" % (s, c))


def main():
    if "--yes" not in sys.argv:
        print(__doc__)
        print("Re-run with --yes to actually do this.")
        return 0

    print("=" * 60)
    print("Live timing test.  THE PRINTER WILL MOVE.  Pen must be off.")
    print("=" * 60)

    turtle.Screen().tracer(0)
    t = Plotter(show_paper=False)
    t.hideturtle()

    wall0 = time.time()
    try:
        t0 = time.time()
        t.connect()
        instrument(t)                 # time everything after the handshake
        connect_secs = time.time() - t0

        t0 = time.time()
        t.prepare()
        prepare_secs = time.time() - t0

        t0 = time.time()
        drawing(t)
        draw_secs = time.time() - t0

        t0 = time.time()
        t.finish()
        finish_secs = time.time() - t0
    except PlotterError as e:
        print("\nStopped: %s" % e)
        return 1

    print("\n%-34s %8s" % ("stage", "seconds"))
    print("-" * 44)
    print("%-34s %8.2f" % ("connect (port + handshake)", connect_secs))
    print("%-34s %8.2f" % ("prepare (home + lift + centre)", prepare_secs))
    print("%-34s %8.2f" % ("DRAWING", draw_secs))
    print("%-34s %8.2f" % ("finish (park + motors off)", finish_secs))
    print("-" * 44)
    print("%-34s %8.2f" % ("wall clock", time.time() - wall0))

    report()
    return 0


if __name__ == "__main__":
    sys.exit(main())
