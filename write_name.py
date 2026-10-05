"""
write_name.py  -  write a name on the AX4 in single-stroke letters.  Teacher tool.

No homing on the AX4: 0,0 is wherever the head sits when the port opens.
Put the head at the BOTTOM-LEFT of the paper first.  The text starts
X_OFF mm right and Y_OFF mm up from there.

    python write_name.py                      # preview PNG only, moves nothing
    python write_name.py --yes                # plot "Kim Sejoung"
    python write_name.py --yes "Other Name"   # letters available: see GLYPHS
    python write_name.py --yes --y 45 "Name"  # baseline 45 mm up (next line)

Pen up M5, pen down M3 S80 (from servo_test.py, 2026-10-04).
"""

import math
import sys
import time

UNIT = 1.5          # mm per font unit; cap height 10 units = 15 mm
GAP = 1.5           # units between letters
X_OFF, Y_OFF = 10.0, 15.0   # baseline start, mm from the bottom-left corner
DRAW_F, TRAVEL_F = 1500, 3000
PEN_UP, PEN_DOWN = "M5", "M3 S80"
SERVO_WAIT = 0.3    # s for the servo to finish moving


def arc(cx, cy, r, a0, a1, n=None):
    """Points on a circle from angle a0 to a1 (degrees, either direction)."""
    n = n or max(4, int(abs(a1 - a0) / 15))
    return [(cx + r * math.cos(math.radians(a0 + (a1 - a0) * i / n)),
             cy + r * math.sin(math.radians(a0 + (a1 - a0) * i / n)))
            for i in range(n + 1)]


def earc(cx, cy, rx, ry, a0, a1, n=None):
    """Like arc() but an ellipse, for the tall round capitals."""
    return [(cx + (x - cx) * rx, cy + (y - cy) * ry)
            for x, y in arc(cx, cy, 1, a0, a1, n)]


# Each glyph: (width, [stroke, ...]); stroke = list of (x, y) points.
# Baseline y=0, x-height 6, cap height 10, descender to -5.
GLYPHS = {
    " ": (4, []),
    "K": (6, [[(0, 0), (0, 10)], [(6, 10), (0, 4)], [(2, 6), (6, 0)]]),
    "S": (6, [arc(3, 7.5, 2.5, 20, 270) + arc(3, 2.5, 2.5, 90, -160)[1:]]),
    "i": (0, [[(0, 0), (0, 6)], [(0, 8), (0, 8.6)]]),
    "j": (1.5, [[(1.5, 6), (1.5, -2.5)] + arc(0, -2.5, 1.5, 0, -180)[1:],
                [(1.5, 8), (1.5, 8.6)]]),
    "m": (7, [[(0, 0), (0, 6)],
              [(0, 3.5)] + arc(1.75, 3.75, 1.75, 180, 0)[1:] + [(3.5, 0)],
              [(3.5, 3.5)] + arc(5.25, 3.75, 1.75, 180, 0)[1:] + [(7, 0)]]),
    "e": (6, [[(0, 3), (6, 3)] + arc(3, 3, 3, 0, 320)[1:]]),
    "o": (6, [arc(3, 3, 3, 90, 450, 24)]),
    "u": (5, [[(0, 6)] + arc(2.5, 2.5, 2.5, 180, 360)[0:] + [(5, 6)],
              [(5, 6), (5, 0)]]),
    "n": (5, [[(0, 0), (0, 6)],
              [(0, 3.5)] + arc(2.5, 3.5, 2.5, 180, 0)[1:] + [(5, 0)]]),
    # Hangeul syllable blocks, 10 x 10 units, built from their jamo.
    "김": (10, [[(0.5, 9.5), (5.5, 9.5), (5.5, 5.8)],               # ㄱ
               [(8, 10), (8, 4.5)],                                 # ㅣ
               [(1.5, 3.5), (7.5, 3.5), (7.5, 0.3), (1.5, 0.3),
                (1.5, 3.5)]]),                                      # ㅁ
    "세": (10, [[(3, 9.5), (0.5, 0.5)], [(2.2, 6.5), (5, 0.5)],     # ㅅ
               [(6.5, 9.5), (6.5, 0.5)], [(5.2, 5.5), (6.5, 5.5)],  # ㅓ
               [(9, 10), (9, 0)]]),                                 # ㅣ
    "정": (10, [[(0.5, 9.5), (5, 9.5)], [(2.75, 9.5), (0.5, 5.5)],
               [(2.3, 8.3), (5, 5.5)],                              # ㅈ
               [(8, 10), (8, 4.5)], [(6, 7.3), (8, 7.3)],           # ㅓ
               arc(4.5, 2.2, 2, 90, 450, 24)]),                     # ㅇ
    "사": (10, [[(3, 9.5), (0.5, 0.5)], [(2.2, 6.5), (5, 0.5)],     # ㅅ
               [(7.5, 10), (7.5, 0)], [(7.5, 5.5), (9.3, 5.5)]]),   # ㅏ
    "랑": (10, [[(0.5, 9.5), (5.5, 9.5), (5.5, 7.4), (0.5, 7.4),
                (0.5, 5.3), (5.8, 5.3)],                            # ㄹ
               [(7.5, 10), (7.5, 4.5)], [(7.5, 7.3), (9.3, 7.3)],   # ㅏ
               arc(4.5, 2.2, 2, 90, 450, 24)]),                     # ㅇ
    "해": (10, [[(2, 9.6), (3.6, 9.6)], [(0.5, 8), (5, 8)],
               arc(2.75, 4.2, 2.3, 90, 450, 24),                    # ㅎ
               [(6.5, 9.5), (6.5, 0.5)], [(6.5, 5.5), (7.8, 5.5)],
               [(9, 10), (9, 0)]]),                                 # ㅐ
    "요": (10, [arc(5, 6.5, 2.8, 90, 450, 24),                      # ㅇ
               [(3.5, 3.3), (3.5, 1.5)], [(6.5, 3.3), (6.5, 1.5)],
               [(0.5, 1.5), (9.5, 1.5)]]),                          # ㅛ
    "v": (6, [[(0, 6), (3, 0), (6, 6)]]),
    "s": (4, [arc(2, 4.5, 1.5, 20, 270) + arc(2, 1.5, 1.5, 90, -160)[1:]]),
    "k": (4.5, [[(0, 10), (0, 0)], [(4.5, 6), (0, 2.5)],
                [(1.5, 3.7), (4.5, 0)]]),
    "b": (6,[[(0, 10), (0, 0)], arc(3, 3, 3, 180, 540, 24)]),
    "r": (4, [[(0, 6), (0, 0)],
              [(0, 3.5)] + arc(2.5, 3.5, 2.5, 180, 60)[1:]]),
    "c": (6, [arc(3, 3, 3, 40, 320)]),
    "l": (0,[[(0, 10), (0, 0)]]),
    "y": (5, [[(0, 6)] + arc(2.5, 2.5, 2.5, 180, 360) + [(5, 6)],
              [(5, 6), (5, -2)] + arc(2.5, -2, 2.5, 0, -160)[1:]]),
    "M": (8,[[(0, 0), (0, 10), (4, 3), (8, 10), (8, 0)]]),
    "p": (6, [[(0, 6), (0, -5)], arc(3, 3, 3, 180, 540, 24)]),
    "h": (5, [[(0, 10), (0, 0)],
              [(0, 3.5)] + arc(2.5, 3.5, 2.5, 180, 0)[1:] + [(5, 0)]]),
    "a": (6, [arc(3, 3, 3, 0, 360, 24), [(6, 6), (6, 0)]]),
    "d": (6, [arc(3, 3, 3, 0, 360, 24), [(6, 10), (6, 0)]]),
    "g": (6, [arc(3, 3, 3, 0, 360, 24),
              [(6, 6), (6, -2)] + arc(3, -2, 3, 0, -160)[1:]]),
    # Rest of the lowercase alphabet
    "f": (3.5, [[(1.5, 0), (1.5, 8.5)] + arc(3, 8.5, 1.5, 180, 60)[1:],
                [(0, 6), (3.5, 6)]]),
    "q": (6, [arc(3, 3, 3, 0, 360, 24), [(6, 6), (6, -5)]]),
    "t": (3.5, [[(1.5, 9), (1.5, 1)] + arc(3, 1, 1.5, 180, 300)[1:],
                [(0, 6), (3.5, 6)]]),
    "w": (8, [[(0, 6), (2, 0), (4, 6), (6, 0), (8, 6)]]),
    "x": (5, [[(0, 6), (5, 0)], [(5, 6), (0, 0)]]),
    "z": (5, [[(0, 6), (5, 6), (0, 0), (5, 0)]]),
    # Rest of the capitals
    "A": (7, [[(0, 0), (3.5, 10), (7, 0)], [(1.3, 3.5), (5.7, 3.5)]]),
    "B": (6.5, [[(0, 5), (0, 10), (3.5, 10)] + arc(3.5, 7.5, 2.5, 90, -90)[1:]
                + [(0, 5)],
                [(3.5, 5)] + arc(4, 2.5, 2.5, 90, -90)[1:] + [(0, 0), (0, 5)]]),
    "C": (8, [earc(4, 5, 4, 5, 45, 315)]),
    "D": (6.5, [[(0, 0), (0, 10), (3, 10)] + earc(3, 5, 3.5, 5, 90, -90)[1:]
                + [(0, 0)]]),
    "E": (6, [[(6, 10), (0, 10), (0, 0), (6, 0)], [(0, 5), (4.5, 5)]]),
    "F": (6, [[(6, 10), (0, 10), (0, 0)], [(0, 5), (4.5, 5)]]),
    "G": (8, [earc(4, 5, 4, 5, 45, 360) + [(4.5, 5)]]),
    "H": (6, [[(0, 0), (0, 10)], [(6, 0), (6, 10)], [(0, 5), (6, 5)]]),
    "I": (0, [[(0, 0), (0, 10)]]),
    "J": (4, [[(4, 10), (4, 3)] + earc(2, 3, 2, 3, 0, -180)[1:]]),
    "L": (5, [[(0, 10), (0, 0), (5, 0)]]),
    "N": (6, [[(0, 0), (0, 10), (6, 0), (6, 10)]]),
    "O": (8, [earc(4, 5, 4, 5, 90, 450, 32)]),
    "P": (6, [[(0, 0), (0, 10), (3.5, 10)] + arc(3.5, 7.5, 2.5, 90, -90)[1:]
              + [(0, 5)]]),
    "Q": (8, [earc(4, 5, 4, 5, 90, 450, 32), [(5, 2), (8, -1)]]),
    "R": (6, [[(0, 0), (0, 10), (3.5, 10)] + arc(3.5, 7.5, 2.5, 90, -90)[1:]
              + [(0, 5)], [(3, 5), (6, 0)]]),
    "T": (7, [[(0, 10), (7, 10)], [(3.5, 10), (3.5, 0)]]),
    "U": (6, [[(0, 10), (0, 3.5)] + earc(3, 3.5, 3, 3.5, 180, 360)[1:]
              + [(6, 10)]]),
    "V": (7, [[(0, 10), (3.5, 0), (7, 10)]]),
    "W": (10, [[(0, 10), (2.5, 0), (5, 10), (7.5, 0), (10, 10)]]),
    "X": (6, [[(0, 10), (6, 0)], [(6, 10), (0, 0)]]),
    "Y": (7, [[(0, 10), (3.5, 5), (7, 10)], [(3.5, 5), (3.5, 0)]]),
    "Z": (6, [[(0, 10), (6, 10), (0, 0), (6, 0)]]),
}


def layout(text):
    """Return strokes in mm, relative to the bottom-left corner."""
    strokes, x = [], 0.0
    for ch in text:
        if ch not in GLYPHS:
            raise SystemExit("No glyph for %r. Available: %s"
                             % (ch, "".join(sorted(GLYPHS))))
        width, glyph = GLYPHS[ch]
        for s in glyph:
            strokes.append([(round(X_OFF + (x + px) * UNIT, 2),
                             round(Y_OFF + py * UNIT, 2)) for px, py in s])
        x += width + GAP
    return strokes


def preview(strokes, path="write_name_preview.png"):
    from PIL import Image, ImageDraw
    xs = [p[0] for s in strokes for p in s]
    ys = [p[1] for s in strokes for p in s]
    k = 6
    x0, y0 = min(0, min(xs)) - 10, min(0, min(ys)) - 10   # always show 0,0
    w = int((max(xs) + 10 - x0) * k)
    h = int((max(ys) + 10 - y0) * k)
    img = Image.new("RGB", (w, h), "white")
    d = ImageDraw.Draw(img)
    ox, oy = -x0 * k, h + y0 * k                          # 0,0 in pixels
    d.line([(ox - 15, oy), (ox + 15, oy)], fill="red")    # origin marker
    d.line([(ox, oy - 15), (ox, oy + 15)], fill="red")
    for s in strokes:
        d.line([(ox + px * k, oy - py * k) for px, py in s],
               fill="black", width=3)
    img.save(path)
    print("Preview: %s   extent X %.1f-%.1f mm, Y %.1f-%.1f mm"
          % (path, min(xs), max(xs), min(ys), max(ys)))


def plot(strokes):
    import serial
    from grbl_connect_test import find_grbl_port, read_until_quiet
    from grbl_motion_test import send

    with serial.Serial(find_grbl_port(), 115200, timeout=0.2) as ser:
        time.sleep(2.0)
        read_until_quiet(ser, quiet=0.5, limit=2.0)
        for cmd in [PEN_UP, "G21", "G90", "G92 X0 Y0"]:
            send(ser, cmd)
        t0 = time.time()
        for i, s in enumerate(strokes, 1):
            x, y = s[0]
            send(ser, "G1 X%.2f Y%.2f F%d" % (x, y, TRAVEL_F))
            send(ser, "G4 P0")                 # arrive before the pen drops
            send(ser, PEN_DOWN)
            send(ser, "G4 P%.2f" % SERVO_WAIT)
            for x, y in s[1:]:
                send(ser, "G1 X%.2f Y%.2f F%d" % (x, y, DRAW_F))
            send(ser, "G4 P0")                 # finish the line before lifting
            send(ser, PEN_UP)
            send(ser, "G4 P%.2f" % SERVO_WAIT)
            print("stroke %d/%d  %.1f s" % (i, len(strokes), time.time() - t0))
        send(ser, "G1 X0 Y0 F%d" % TRAVEL_F)
        send(ser, "G4 P0")
        print("Done in %.1f s, head back at start." % (time.time() - t0))


def main():
    global Y_OFF
    args = [a for a in sys.argv[1:] if a != "--yes"]
    if args[:1] == ["--y"]:             # baseline height in mm, for a 2nd line
        Y_OFF = float(args[1])
        args = args[2:]
    text = args[0] if args else "Kim Sejoung"
    strokes = layout(text)
    preview(strokes)
    if "--yes" in sys.argv:
        plot(strokes)
    else:
        print("Preview only. Add --yes to plot.")


if __name__ == "__main__":
    main()
