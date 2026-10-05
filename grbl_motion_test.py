"""
grbl_motion_test.py  -  AX4 first axis move.  Teacher tool.

The AX4 has no homing or limit switches: 0,0 is wherever the head sits when
the board resets (which happens when this script opens the port).  So push
the head by hand to the FRONT-LEFT corner before running.

Pen stays UP (M5) the whole time.  Moves, at F1000 (~17 mm/s):
    X+20,  then Y+20,  then back to 0,0
After each move it waits for motion to finish (G4 P0) and prints the
reported position and the time taken.

    python grbl_motion_test.py          # prints the plan, moves nothing
    python grbl_motion_test.py --yes    # actually moves
"""

import sys
import time

import serial

from grbl_connect_test import find_grbl_port, read_until_quiet

MOVES = ["G1 X20 Y0 F1000", "G1 X20 Y20 F1000", "G1 X0 Y0 F1000"]


def send(ser, cmd, limit=30.0):
    ser.write((cmd + "\n").encode("ascii"))
    t_end = time.time() + limit
    while time.time() < t_end:
        line = ser.readline().decode("ascii", "replace").strip()
        if line == "ok":
            return
        if line.startswith(("error", "ALARM")):
            raise RuntimeError("%s -> %s" % (cmd, line))
    raise RuntimeError("%s -> no ok after %.0f s" % (cmd, limit))


def status(ser):
    ser.write(b"?")
    for line in read_until_quiet(ser, quiet=0.3, limit=2.0):
        if line.startswith("<"):
            return line
    return "(no status)"


def main():
    print(__doc__)
    if "--yes" not in sys.argv:
        print("Plan only. Add --yes to move.")
        return 0

    with serial.Serial(find_grbl_port(), 115200, timeout=0.2) as ser:
        time.sleep(2.0)
        print("Banner:", read_until_quiet(ser, quiet=0.5, limit=2.0))
        for cmd in ["M5", "G21", "G90", "G92 X0 Y0"]:
            send(ser, cmd)
        print("Start:", status(ser))

        for cmd in MOVES:
            t0 = time.time()
            send(ser, cmd)
            t_ok = time.time() - t0
            send(ser, "G4 P0")          # GRBL's "wait until motion is done"
            print("%-18s ok after %.2f s, done after %.2f s   %s"
                  % (cmd, t_ok, time.time() - t0, status(ser)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
