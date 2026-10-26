# Like the students' portrait.py: one line for every dark cell.
import turtle
from photo_tools import load_photo, preview, show_numbers

pixels = load_photo("dots.png", 4, contrast=False)   # really Dots.PNG
preview(pixels)
show_numbers(pixels)

t = turtle.Turtle()
for row in range(len(pixels)):
    for col in range(len(pixels[0])):
        if pixels[row][col] < 128:
            t.penup()
            t.goto(col * 10, -row * 10)
            t.pendown()
            t.forward(5)
turtle.done()
