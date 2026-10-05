"""
hello_shapes.py  -  a short first program for the plotter.

Uses a function, parameters, and a list - the three things the Turtle unit
is about.

Run it with LIVE = False first to see it on screen.
Change to LIVE = True to draw it for real.
"""

from plotter import Plotter

LIVE = False          # <-- set True when the USB cable is connected

t = Plotter(live=LIVE)


def square(size):
    """Draw a square with sides `size` long, ending where it started."""
    for i in range(4):
        t.forward(size)
        t.left(90)


def move_to(x, y):
    """Lift the pen, go somewhere, put the pen back down."""
    t.penup()
    t.goto(x, y)
    t.pendown()


# A list of sizes, drawn one after another.
sizes = [40, 60, 80, 100]

x = -260
for size in sizes:
    move_to(x, -100)
    square(size)
    x = x + size + 20

t.penup()

t.save_svg("hello_shapes.svg")
t.save_gcode("hello_shapes.gcode")
t.finish()

t.hideturtle()
import turtle
turtle.done()
