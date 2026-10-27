"""
photo_tools.py  -  turns a photo into a grid of brightness numbers.

You don't need to read or change this file. Use it like this:

    from photo_tools import load_photo

    pixels = load_photo("dog.jpg", 30)

Put your photo in the photos folder first. The second number is how many
columns (cells across) you want. The rows are worked out for you.

You get back a list of lists:
    pixels[0]       is the TOP row of the picture
    pixels[0][0]    is the top-left cell
    each number is a brightness: 0 is black, 255 is white

Other tools in this file:
    show_numbers(pixels)    prints the numbers so you can read them or paste them
    preview(pixels)         opens a picture of your grid in a separate window
    fit_to_sheet(pixels)    gives you SIZE, LEFT, TOP so the grid fills the sheet
"""

import os
import sys

PHOTO_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "photos")
SHEET_WIDTH = 500
SHEET_HEIGHT = 350
SLOW_COLUMNS = 60      # above this, warn: slow on screen, long on the plotter
MAX_COLUMNS = 200      # above this, refuse
IMAGE_TYPES = (".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".heic", ".heif")


class PhotoError(SystemExit):
    """A problem with the photo or the numbers given to load_photo.
    It stops the program and shows only the message (no scary traceback)."""


def _pillow():
    try:
        from PIL import Image, ImageOps
    except ImportError:
        raise PhotoError(
            "\n\nThe Pillow package isn't installed, so photos can't be opened.\n"
            "In Thonny: Tools > Manage packages... > search 'pillow' > Install.\n"
            "Then run your program again."
        ) from None
    return Image, ImageOps


def _photo_files():
    if not os.path.isdir(PHOTO_FOLDER):
        return []
    return sorted(f for f in os.listdir(PHOTO_FOLDER)
                  if f.lower().endswith(IMAGE_TYPES) and not f.startswith("."))


def _find(filename):
    """Return the full path to the photo, or raise a helpful error."""
    if not isinstance(filename, str):
        raise PhotoError(
            "\n\nThe photo's name needs to be in quotes, like this:\n"
            '    load_photo("dog.jpg", 30)'
        )
    # allow "photos/dog.jpg" or a full path as well as just "dog.jpg"
    if os.path.isfile(filename):
        return filename
    path = os.path.join(PHOTO_FOLDER, os.path.basename(filename))
    if os.path.isfile(path):
        return path

    files = _photo_files()
    msg = "\n\nCouldn't find a photo named '" + filename + "' in the photos folder.\n"
    same_but_case = [f for f in files if f.lower() == os.path.basename(filename).lower()]
    if same_but_case:
        msg += ("Did you mean '" + same_but_case[0] + "'? "
                "Capital letters count: 'Dog.JPG' and 'dog.jpg' are different names.\n")
    elif "." not in os.path.basename(filename):
        matches = [f for f in files if os.path.splitext(f)[0].lower() == filename.lower()]
        if matches:
            msg += "Did you mean '" + matches[0] + "'? Include the ending, like .jpg or .png.\n"
        else:
            msg += "Remember the ending, like .jpg or .png.\n"
    if files:
        msg += "Photos in the folder right now: " + ", ".join(files)
    elif os.path.isdir(PHOTO_FOLDER):
        msg += "The photos folder is empty. Drag your photo into it first."
    else:
        msg += "There's no photos folder next to photo_tools.py. Make one and put your photo in it."
    raise PhotoError(msg)


def _open(path):
    Image, ImageOps = _pillow()
    is_heic = path.lower().endswith((".heic", ".heif"))
    if is_heic:
        try:
            from pillow_heif import register_heif_opener
            register_heif_opener()
        except ImportError:
            raise PhotoError(
                "\n\n" + os.path.basename(path) + " is a HEIC photo (the iPhone format), "
                "which can't be opened here.\nSave it as a JPG instead, then use that name:\n"
                "  - Mac: open it in Preview > File > Export > Format: JPEG\n"
                "  - Or AirDrop/email it to yourself as 'Most Compatible'\n"
                "  - Or in Thonny, install the package 'pillow-heif' and run again."
            ) from None
    try:
        img = Image.open(path)
        img.load()
    except Exception:
        raise PhotoError(
            "\n\n'" + os.path.basename(path) + "' couldn't be opened as a picture.\n"
            "Make sure it's a real photo file (.jpg or .png work best)."
        ) from None
    img = ImageOps.exif_transpose(img)          # phone photos are often stored sideways

    if is_heic:
        # Save a JPG copy so the plotter (which may not read HEIC) can open it too.
        jpg = os.path.splitext(path)[0] + ".jpg"
        if not os.path.exists(jpg):
            img.convert("RGB").save(jpg, quality=92)
            print("Saved a JPG copy: " + os.path.basename(jpg) +
                  ". Use that name instead, and push it to GitHub with your code.")
    return img


def load_photo(filename, columns, rotate=0, square=False, contrast=True, quiet=False):
    """
    Open a photo from the photos folder and return it as a grid of
    brightness numbers (a list of rows, top row first).

    Required:
    filename  the photo's name, in quotes, like "dog.jpg"
    columns   how many cells across, like 30

    Optional (leave them out and you get the defaults):
    rotate    turns the photo clockwise: 0 (default), 90, 180, or 270.
              Phone photos are turned upright for you, so you only need this
              if your photo still comes out sideways or upside down.
    square    False (default) keeps the whole photo.
              True cuts the left and right (or top and bottom) off evenly,
              leaving a square from the middle.
    contrast  True (default) makes the darkest part near-black and the
              lightest part near-white. False keeps the photo as it is.
    quiet     False (default) prints the grid size. True prints nothing.

    Examples:
        load_photo("dog.jpg", 30)
        load_photo("dog.jpg", 30, rotate=90)
        load_photo("dog.jpg", 30, square=True)
    """
    if isinstance(columns, float) and columns.is_integer():
        columns = int(columns)
    if not isinstance(columns, int) or isinstance(columns, bool):
        raise PhotoError(
            "\n\nThe number of columns should be a whole number without quotes, like this:\n"
            '    load_photo("dog.jpg", 30)'
        )
    if columns < 2:
        raise PhotoError("\n\nUse at least 2 columns. Try something between 15 and 40.")
    if columns > MAX_COLUMNS:
        raise PhotoError("\n\n" + str(columns) + " columns is far too many for the plotter. "
                         "Try something between 15 and 40.")

    if rotate not in (0, 90, 180, 270, -90, 360):
        raise PhotoError(
            "\n\nrotate can be 0, 90, 180, or 270 (degrees clockwise), like this:\n"
            '    load_photo("dog.jpg", 30, rotate=90)'
        )
    if not isinstance(square, bool) or not isinstance(contrast, bool):
        raise PhotoError("\n\nsquare and contrast are True or False, with a capital letter "
                         "and no quotes, like this:\n    load_photo(\"dog.jpg\", 30, square=True)")

    path = _find(filename)
    Image, ImageOps = _pillow()
    img = _open(path)

    turn = rotate % 360
    if turn:
        # Pillow turns counter-clockwise, so 90 clockwise is 270 its way
        img = img.rotate(-turn, expand=True)
    if square:
        w, h = img.size
        side = min(w, h)
        left, top = (w - side) // 2, (h - side) // 2
        img = img.crop((left, top, left + side, top + side))

    # transparent parts become white paper, not black
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        img = img.convert("RGBA")
        paper = Image.new("RGBA", img.size, (255, 255, 255, 255))
        img = Image.alpha_composite(paper, img)
    gray = img.convert("L")
    if contrast:
        gray = ImageOps.autocontrast(gray, cutoff=1)

    width, height = gray.size
    rows = max(1, round(columns * height / width))
    small = gray.resize((columns, rows), Image.BOX)   # each cell = the average of its patch
    pixels = [[small.getpixel((col, row)) for col in range(columns)] for row in range(rows)]

    if not quiet:
        cells = columns * rows
        print(os.path.basename(path) + " -> " + str(columns) + " columns x " + str(rows) +
              " rows = " + format(cells, ",") + " cells")
        if columns > SLOW_COLUMNS:
            print("  Heads up: that's a lot of cells. It will draw slowly on screen and "
                  "take a long time on the plotter.")
    return pixels


def show_numbers(pixels, name="pixels"):
    """Print the grid as Python you could paste into a program."""
    widest = max(len(str(v)) for row in pixels for v in row)
    print(name + " = [")
    for row in pixels:
        print("    [" + ", ".join(str(v).rjust(widest) for v in row) + "],")
    print("]")


def fit_to_sheet(pixels):
    """
    Return SIZE, LEFT, TOP so the whole grid fits the sheet, centered.
        SIZE, LEFT, TOP = fit_to_sheet(pixels)
    (x, y) of a cell's bottom-left corner is then
        x = LEFT + col * SIZE
        y = TOP - (row + 1) * SIZE
    """
    rows, columns = len(pixels), len(pixels[0])
    size = min(SHEET_WIDTH / columns, SHEET_HEIGHT / rows)
    left = -size * columns / 2
    top = size * rows / 2
    return size, left, top


def preview(pixels, scale=None):
    """
    Open a picture of the grid in its own window: each cell one gray square.
    It doesn't use turtle, so it never ends up on the plotter.
    The picture is also saved as preview.png next to photo_tools.py.
    """
    Image, ImageOps = _pillow()
    rows, columns = len(pixels), len(pixels[0])
    small = Image.new("L", (columns, rows))
    small.putdata([v for row in pixels for v in row])
    if scale is None:
        scale = max(1, 600 // max(columns, rows))
    big = small.resize((columns * scale, rows * scale), Image.NEAREST)
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "preview.png")
    big.save(out)
    no_screen = sys.platform.startswith("linux") and not (
        os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
    if no_screen:
        print("Saved preview.png (no screen here to show it on).")
        return
    try:
        big.show()
    except Exception:
        print("Saved preview.png (couldn't open a window to show it).")


if __name__ == "__main__":
    # Running this file on its own lists the photos it can see.
    files = _photo_files()
    if files:
        print("Photos ready to use:", ", ".join(files))
    else:
        print("No photos yet. Put one in the photos folder next to this file.")
