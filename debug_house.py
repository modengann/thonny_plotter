import turtle

t = turtle.Turtle()

def house(x = 50, y = 100):
    t.penup()
    t.goto(x, y)
    t.pendown()
    for i in range(4):
        t.forward(60)
        t.left(90)
    t.left(90)
    t.forward(60)
    t.right(90)

    # roof:
    t.forward(60)
    t.left(120)
    t.forward(60)
    t.left(120)
    t.forward(60)
    t.setheading(0)

house()
house(y = 50)
house(-150, -50)
house(100, -50)

turtle.done()