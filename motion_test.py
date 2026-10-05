"""
motion_test.py  -  Phase 3 check.  Teacher tool.

Non-interactive replacement for the old --jog prompt.  It connects, homes,
exercises Z, walks the four corners of the paper at a safe height, and parks.
Every step is timed and printed.

*** THIS MOVES THE PRINTER. ***

It sends G28, which homes Z by probing the bed.  Run it with the pen
REMOVED or fully RETRACTED, or the pen will be driven into the bed.

Note: this firmware reports EMERGENCY_PARSER:0, so an M112 sent over the
serial port is queued behind whatever is already running and will NOT stop
the machine straight away.  The power switch is the real emergency stop.

    python motion_test.py              # explains itself, moves nothing
    python motion_test.py --yes        # actually runs
    python motion_test.py --yes COM10  # and names the port
"""

import sys
import time

from plotter import Plotter, PlotterError, find_prusa_port, serial

SAFE_Z = 10.0          # mm - well clear of the bed for travel moves
PAPER_MM = 150.0
BED_MM = 180.0

LO = BED_MM / 2 - PAPER_MM / 2      # 15 mm
HI = BED_MM / 2 + PAPER_MM / 2      # 165 mm

CORNERS = [
    ("front left",  LO, LO),
    ("front right", HI, LO),
    ("back right",  HI, HI),
    ("back left",   LO, HI),
]


def bare_plotter():
    """A Plotter with no turtle window - this is a teacher tool."""
    p = Plotter.__new__(Plotter)
    p.ser = None
    p._hw_down = False
    p._homed = False
    p.firmware = None
    p.pen_up_z = SAFE_Z
    p.pen_down_z = 1.0
    p.bed_mm = BED_MM
    p.travel_feed = 3000
    p.pen_offset = (0.0, 0.0)
    return p


def timed(p, label, command, timeout=30):
    """Send one command, wait for it to actually finish, and time it."""
    t0 = time.time()
    p._send(command, timeout=timeout)
    p._send("M400", timeout=timeout)       # wait for the move to complete
    secs = time.time() - t0
    print("  %-26s %-28s %6.2fs" % (label, command, secs))
    return secs


def explain():
    print(__doc__)
    print("Planned sequence (nothing has been sent):")
    print("  1. connect, heaters off            (no movement)")
    print("  2. G28                             HOME ALL AXES - probes the bed")
    print("  3. G1 Z10                          lift to 10 mm")
    print("  4. G1 Z5                           down to 5 mm")
    print("  5. G1 Z10                          back to safe height")
    for i, (name, x, y) in enumerate(CORNERS, start=6):
        print("  %d. G1 X%.1f Y%.1f%s%s at Z10" % (i, x, y, " " * 8, name))
    print("  %d. park at X0 Y170, motors off" % (6 + len(CORNERS)))
    print()
    print("Re-run with --yes to actually do this.")


def main():
    args = [a for a in sys.argv[1:]]
    if "--yes" not in args:
        explain()
        return 0
    args.remove("--yes")
    port = args[0] if args else find_prusa_port()

    if serial is None:
        print("pyserial is not installed.")
        return 1

    print("=" * 70)
    print("Phase 3: motion test.  THE PRINTER WILL MOVE.")
    print("The pen must be removed or fully retracted.")
    print("=" * 70)

    p = bare_plotter()
    try:
        fw = p.connect(port)
    except PlotterError as e:
        print("\n" + str(e))
        return 1
    print("Firmware: %s\n" % fw.split(" SOURCE_CODE_URL")[0])

    total0 = time.time()
    try:
        print("Step / command / time:")
        timed(p, "home all axes", "G28", timeout=240)
        print("    (position after homing: %s)"
              % (p._send("M114", collect=True) or ["?"])[0])

        timed(p, "Z up to 10", "G1 Z10.000 F600")
        timed(p, "Z down to 5", "G1 Z5.000 F600")
        timed(p, "Z back to safe 10", "G1 Z%.3f F600" % SAFE_Z)

        print("  -- four corners of the paper at Z%.0f --" % SAFE_Z)
        corner_times = []
        for name, x, y in CORNERS:
            corner_times.append(
                timed(p, name, "G1 X%.3f Y%.3f F%d" % (x, y, p.travel_feed)))

        timed(p, "back to paper centre", "G1 X90.000 Y90.000 F%d" % p.travel_feed)

        print("\n  Final position: %s"
              % (p._send("M114", collect=True) or ["?"])[0])
        print("  Corner-to-corner moves: %.2fs min, %.2fs max, %.2fs total"
              % (min(corner_times), max(corner_times), sum(corner_times)))
        print("  Whole sequence: %.1fs" % (time.time() - total0))

    except PlotterError as e:
        print("\nStopped because of a problem:\n" + str(e))
        try:
            p._send("G1 Z%.3f F600" % SAFE_Z)   # get clear of the bed
            p._send("M84")
        except Exception:
            pass
        p.ser.close()
        return 1

    print("\nParking and releasing the motors.")
    timed(p, "park", "G1 X0.000 Y170.000 F%d" % p.travel_feed)
    p._send("M84")
    p.ser.close()
    p.ser = None
    print("Done.  Motors released.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
