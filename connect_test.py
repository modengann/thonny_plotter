"""
connect_test.py  -  Phase 2 check.  Teacher tool.

Finds the printer, opens the serial port, asks the firmware to identify
itself with M115, and prints what came back.

THIS MOVES NOTHING.  It sends no G28 and no G1.  It is safe to run with the
pen fitted.

    python connect_test.py            # find the printer automatically
    python connect_test.py COM5       # or name the port yourself
"""

import sys
import time

from plotter import (Plotter, PlotterError, find_ports, find_prusa_port,
                     PRUSA_VID, serial)


def main():
    print("=" * 62)
    print("Phase 2: connection check (read-only - nothing will move)")
    print("=" * 62)

    if serial is None:
        print("\npyserial is not installed in this Python.")
        print("Install it with:  python -m pip install pyserial")
        return 1

    # ---- 1. what ports exist? -------------------------------------------
    print("\nSerial ports this computer can see:")
    ports = find_ports()
    if not ports:
        print("  (none)")
        print("\nNo serial ports at all.  The printer is off, the cable is")
        print("not plugged in, or the cable is charge-only with no data wires.")
        return 1
    for dev, desc, vid in ports:
        tag = "   <-- Prusa (vid 0x%04X)" % vid if vid == PRUSA_VID else ""
        print("  %-24s %s%s" % (dev, desc, tag))

    port = sys.argv[1] if len(sys.argv) > 1 else find_prusa_port()
    if port is None:
        print("\nNone of those look like the printer.")
        print("If you know which one it is, run:  python connect_test.py COM5")
        return 1
    print("\nUsing port: %s" % port)

    # ---- 2. open it and say hello ---------------------------------------
    p = Plotter.__new__(Plotter)      # no turtle window for a teacher tool
    p.ser = None
    p._hw_down = False
    p._homed = False
    p.firmware = None
    p.pen_up_z = 5.0
    p.pen_down_z = 1.0

    t0 = time.time()
    try:
        firmware = p.connect(port)
    except PlotterError as e:
        print("\n" + str(e))
        return 1
    open_secs = time.time() - t0

    print("\nFirmware replied to M115:")
    if firmware:
        for part in firmware.split(" | "):
            print("  " + part)
    else:
        print("  (nothing - see HARDWARE_NOTES.md)")

    # ---- 3. a few more read-only queries --------------------------------
    print("\nOther read-only checks:")
    for cmd, label in [("M105", "temperatures"), ("M114", "position")]:
        t1 = time.time()
        try:
            reply = p._send(cmd, collect=True)
            print("  %-5s %-14s %.2fs  %s"
                  % (cmd, label, time.time() - t1,
                     " / ".join(reply) if reply else "(no detail)"))
        except PlotterError as e:
            print("  %-5s %-14s failed: %s" % (cmd, label, e))

    print("\nHandshake took %.1fs including the board's reboot delay." % open_secs)
    print("Closing the port.  Nothing moved.")
    p.ser.close()
    p.ser = None
    return 0


if __name__ == "__main__":
    sys.exit(main())
