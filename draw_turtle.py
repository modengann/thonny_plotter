"""
draw_turtle.py  -  draw a turtle (the animal) on the AX4.  Teacher tool.

Top view, facing right, about 76 x 70 mm, CENTRED on wherever the head sits
when the port opens.  Put the head in the middle of the paper first.

    python draw_turtle.py          # preview PNG only, moves nothing
    python draw_turtle.py --yes    # plot it
"""

import math
import sys

from write_name import arc, earc, plot, preview

SHELL_RX, SHELL_RY = 30, 22


def shell_y(x):
    """Upper edge of the shell ellipse at x."""
    return SHELL_RY * math.sqrt(1 - (x / SHELL_RX) ** 2)


def leg(a, b, tip, w=5):
    """A rounded flipper from shell point a, around tip, back to shell point b."""
    mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
    ang = math.degrees(math.atan2(tip[1] - my, tip[0] - mx))
    side = math.cos(math.radians(ang + 90)) * (a[0] - mx) + \
        math.sin(math.radians(ang + 90)) * (a[1] - my)
    a0, a1 = (ang + 90, ang - 90) if side > 0 else (ang - 90, ang + 90)
    return [a] + arc(tip[0], tip[1], w, a0, a1, 12) + [b]


def turtle_strokes():
    s = [earc(0, 0, SHELL_RX, SHELL_RY, 0, 360, 48)]           # shell

    hexagon = [(12 * math.cos(math.radians(a)), 9 * math.sin(math.radians(a)))
               for a in range(0, 361, 60)]
    s.append(hexagon)                                          # shell pattern
    for a in range(0, 360, 60):
        r = math.radians(a)
        s.append([(12 * math.cos(r), 9 * math.sin(r)),
                  (SHELL_RX * math.cos(r), SHELL_RY * math.sin(r))])

    nx = SHELL_RX * math.sqrt(1 - (5.1 / SHELL_RY) ** 2)       # neck on shell
    s.append([(nx, 5.1)] + arc(40, 0, 8, 140, -140, 20) + [(nx, -5.1)])
    s.append(arc(43, 3, 1, 0, 360, 8))                         # eye

    for sx in (1, -1):                                         # 4 legs
        for sy in (1, -1):
            a = (sx * 10, sy * shell_y(10))
            b = (sx * 22, sy * shell_y(22))
            s.append(leg(a, b, (sx * 26, sy * 30)))

    tx = -SHELL_RX * math.sqrt(1 - (4 / SHELL_RY) ** 2)        # tail
    s.append([(tx, 4), (-38, 0), (tx, -4)])
    return [[(round(x, 2), round(y, 2)) for x, y in st] for st in s]


if __name__ == "__main__":
    strokes = turtle_strokes()
    preview(strokes, "draw_turtle_preview.png")
    if "--yes" in sys.argv:
        plot(strokes)
    else:
        print("Preview only. Add --yes to plot.")
