"""
grbl_connect_test.py  -  AX4 (GRBL) connection check.  Teacher tool.

Opens the plotter's serial port, reads the GRBL start-up banner, then asks
for settings ($$), build info ($I) and status (?).  Prints everything.

THIS MOVES NOTHING.  It sends no G0/G1, no $H (home), no $X (unlock), and no
M3/M5 (pen servo).  Note: opening the port resets the controller board, so
the pen servo may twitch once as it boots.  That is normal.

    python grbl_connect_test.py            # first CH340 port found
    python grbl_connect_test.py COM12      # or name the port yourself
"""

import sys
import time

import serial
from serial.tools import list_ports

CH340_VID = 0x1A86


def find_grbl_port():
    for p in list_ports.comports():
        if p.vid == CH340_VID:
            return p.device
    return None


def read_until_quiet(ser, quiet=0.5, limit=5.0):
    """Collect lines until nothing arrives for `quiet` seconds."""
    lines = []
    t_end = time.time() + limit
    last = time.time()
    while time.time() < t_end:
        raw = ser.readline()
        if raw:
            lines.append(raw.decode("ascii", "replace").rstrip())
            last = time.time()
        elif time.time() - last > quiet:
            break
    return lines


def ask(ser, cmd, realtime=False):
    print("\n>>> %s" % cmd)
    t0 = time.time()
    ser.write(cmd.encode("ascii") if realtime else (cmd + "\n").encode("ascii"))
    for line in read_until_quiet(ser):
        print("    %s" % line)
    print("    (%.2f s)" % (time.time() - t0))


def main():
    print("Serial ports:")
    for p in list_ports.comports():
        print("  %-8s %s" % (p.device, p.description))

    port = sys.argv[1] if len(sys.argv) > 1 else find_grbl_port()
    if port is None:
        print("\nNo CH340 port found. Is the AX4 powered and plugged in?")
        return 1
    print("\nUsing %s at 115200" % port)

    with serial.Serial(port, 115200, timeout=0.2) as ser:
        t0 = time.time()
        print("\nStart-up banner (board resets when the port opens):")
        banner = read_until_quiet(ser, quiet=1.0, limit=4.0)
        for line in banner:
            print("    %s" % line)
        if not banner:
            print("    (nothing - try 9600 baud, or the board did not reset)")
        print("    (%.2f s)" % (time.time() - t0))

        ask(ser, "$I")
        ask(ser, "$$")
        ask(ser, "?", realtime=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
