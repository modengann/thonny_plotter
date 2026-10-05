"""
demo_spiral.py  -  sample program for the plotter.

Run it with the printer unplugged first: it draws on screen and saves
an SVG and a G-code file.  Then plug the printer in and change
LIVE = False to LIVE = True to watch the pen draw the same thing.

The pen heights for this printer live in plotter_config.json and are
loaded for you, so there are no machine numbers in this file.

The paper is a 150 mm square.  1 turtle unit = 0.25 mm, so the paper
runs from -300 to +300 in both directions.
"""

from plotter import Plotter

LIVE = False          # <-- set True when the USB cable is connected

t = Plotter(live=LIVE)


def polygon(sides, size):
    """Draw a regular polygon and return to where we started."""
    for i in range(sides):
        t.forward(size)
        t.left(360 / sides)


def spiral_of(sides, count, step, turn):
    """Draw `count` polygons, each `step` bigger and turned by `turn` degrees."""
    size = 40
    for i in range(count):
        polygon(sides, size)
        t.left(turn)
        size = size + step


# --- start in the centre, pen up, facing right ---------------------------
t.penup()
t.goto(0, 0)
t.setheading(0)
t.pendown()

spiral_of(sides=4, count=10, step=8, turn=10)

t.penup()

# --- a signature in the corner ------------------------------------------
t.goto(-280, -280)
t.setheading(0)
t.pendown()
polygon(3, 30)
t.penup()

# --- outputs --------------------------------------------------------------
t.save_svg("spiral.svg")
t.save_gcode("spiral.gcode")
t.finish()                 # safe to call even when not connected

t.hideturtle()
import turtle
turtle.done()
