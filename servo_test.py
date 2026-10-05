"""
servo_test.py  -  AX4 pen-lift servo test.  Teacher tool.

Steps the pen servo through a list of M3 S values, holding each one, so the
teacher can watch which value lifts the pen and which lowers it.  Each step
beeps (Windows) and prints the S value in large text.

Moves ONLY the pen servo.  Sends no G0/G1, no $H, no $X.

    python servo_test.py                    # default sweep
    python servo_test.py 0 40 0 40          # your own S values
    python servo_test.py --hold 3 50 60 70  # hold each value 3 s
"""

import sys
import time

import serial

try:
    import winsound          # Windows only: beep so the teacher can count steps
except ImportError:
    winsound = None

from grbl_connect_test import find_grbl_port, read_until_quiet

HOLD = 5.0
DEFAULT = [0, 250, 500, 750, 1000]


def send(ser, cmd):
    ser.write((cmd + "\n").encode("ascii"))
    replies = read_until_quiet(ser, quiet=0.3, limit=3.0)
    return " / ".join(r for r in replies if r) or "(no reply)"


def main():
    global HOLD
    args = sys.argv[1:]
    if args[:1] == ["--hold"]:
        HOLD = float(args[1])
        args = args[2:]
    values = [int(v) for v in args] or DEFAULT
    port = find_grbl_port()
    if port is None:
        print("No CH340 port found.")
        return 1

    with serial.Serial(port, 115200, timeout=0.2) as ser:
        banner = read_until_quiet(ser, quiet=1.0, limit=5.0)
        print("Banner: %s" % " / ".join(l for l in banner if l))

        for n in range(5, 0, -1):
            print("starting in %d" % n)
            time.sleep(1)

        t0 = time.time()
        steps = ["M5"] + ["M3 S%d" % v for v in values] + ["M5"]
        for i, cmd in enumerate(steps, 1):
            if winsound:
                winsound.Beep(880, 900 if cmd == "M5" else 150)
            reply = send(ser, cmd)
            print("\n" + "=" * 40)
            print("   step %d of %d      %s" % (i, len(steps), cmd))
            print("=" * 40)
            print("%5.1f s  -> %s" % (time.time() - t0, reply))
            time.sleep(HOLD)
    return 0


if __name__ == "__main__":
    code = main()
    input("\nDone. Press Enter to close.")
    sys.exit(code)
