# My Pixels in Ink portrait
# Name: ______________________

import turtle
from photo_tools import load_photo, preview, show_numbers
SHEET_W = 278 # landscape A4; for portrait use 210
SHEET_H = 215 # landscape A4; for portrait use 297
screen = turtle.Screen()
screen.setup(width=SHEET_W * 3, height=SHEET_H * 3) # window shaped like the paper
screen.setworldcoordinates(0, -SHEET_H, SHEET_W, 0) # to

screen.tracer(0)


# ---------------------------------------------------------------
# 1. YOUR PHOTO
#    Drag your photo into the photos folder, then set these two lines.
# ---------------------------------------------------------------
PHOTO = "images.jpg"     # the photo's exact name, in quotes (capitals count)
COLUMNS = 40          # how many cells across. Rows are worked out for you.

pixels = load_photo(PHOTO, COLUMNS)

# pixels is a list of rows, TOP row first.
#   pixels[row][col] is one cell's brightness: 0 = black, 255 = white
#   len(pixels)      is how many rows
#   len(pixels[0])   is how many columns
#
# Need more? Add any of these inside load_photo( ... ):
#   rotate=90       turn the photo clockwise (90, 180, or 270) if it comes out sideways
#   square=True     keep only a square from the middle of the photo
#   contrast=False  skip the automatic darkening/lightening
# Example:  pixels = load_photo(PHOTO, COLUMNS, rotate=90, square=True)
#
# Helpers for testing (delete before you plot):
#   preview(pixels)        shows your grid as gray squares in its own window
#   show_numbers(pixels)   prints every number
# show_numbers(pixels)



# ---------------------------------------------------------------
# 2. YOUR TURTLE
# ---------------------------------------------------------------
t = turtle.Turtle()
t.speed(0)


# ---------------------------------------------------------------
# 3. YOUR FUNCTIONS
#    Your shading functions, your key, your cell(). Paste or write them here.
# ---------------------------------------------------------------



# ---------------------------------------------------------------
# 4. YOUR DRAWING
#    Loop through pixels and draw every cell. Remember: row 0 is the TOP.
# ---------------------------------------------------------------

t.speed(0)
t.hideturtle()
def box(x,y,size):
    t.penup()
    t.goto(x,y)
    t.pendown()
    t.goto(x+size,y)
    t.goto(x+size, y + size)
    t.goto(x, y+size)
    t.goto(x,y)


def sideways(x,y,size):
    
    t.penup()
    t.goto(x,y)
    t.pendown()
    t.forward(size)
    
    
def vertical(x,y,size):
    t.penup()
    t.goto(x,y)
    t.pendown()
    t.goto(x,y+size)
    
def multidraw(x_start,y_start,size,density):
    
    x = x_start
    y = y_start
    box(x,y,size)
    #Horizontal lines
    y += size/(density + 1)
    for i in range(density):
        sideways(x,y,size)
        y += size/(density + 1)

    x = x_start
    y = y_start
    x += size/(density + 1)
    for i in range(density):
        vertical(x,y,size)
        x += size/(density + 1)
    
        
    
        
    
# multidraw(0,0,125,row)



 
x = 0
y = 0
size = 5
def car ():
    if pixel <= 51:
             multidraw(x,y,size,5)
    elif pixel <= 102:
             multidraw(x,y,size,4)
    elif pixel <= 153:
             multidraw(x,y,size,3)
    elif pixel <= 204:
             multidraw(x,y,size,2)
    else:
             multidraw(x,y,size,1)

 




for row in pixels:
    for pixel in row:
        car()
        x += size
    x = 0
    y -= size
#     car()
#     print(row)



screen.update()

turtle.done()
