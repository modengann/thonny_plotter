# SETUP - Thonny to the Prusa MINI

Written for the teacher. Covers what to install, how a student's program
reaches the printer, and what to do when it doesn't.

---

## 1. Thonny and Python

**Good news: there is probably nothing to install.**

Thonny on this machine bundles **Python 3.10.11**, and **pyserial 3.5 is
already in it** - Thonny ships pyserial for its MicroPython support, and that
is the same library this project uses.

Verified on the teacher's laptop:

```
C:\Users\cmoden\AppData\Local\Programs\Thonny\python.exe --version
  Python 3.10.11
  pyserial 3.5
```

Both test suites and the port detection run correctly under Thonny's own
interpreter, not just a system Python.

### Checking a student's laptop

Have them open Thonny and run this one-liner in the shell at the bottom:

```python
import serial; print(serial.__version__)
```

- Prints a version (e.g. `3.5`) - nothing to do.
- `ModuleNotFoundError` - Tools > Manage packages, type `pyserial`, Install,
  then restart Thonny. No admin rights needed; it installs into the user's
  own Thonny.

**Do not install `serial`.** That is a different, unrelated package and it will
break the import. The name to type is `pyserial`.

### Which Python is Thonny using?

The bottom-right corner of the Thonny window shows the interpreter. It should
say the bundled Python, not a system one. If a student has a system Python
selected, pyserial may be missing there even though Thonny's own copy has it.
Run > Configure interpreter to switch back.

---

## 2. The files a student needs

Both files go in the **same folder**, and the student's program must be saved
into that folder too:

- `plotter.py` - the library. One file, dropped next to their script.
- `plotter_config.json` - this printer's pen heights. Written by the
  calibration tool; students never open or edit it.

`plotter.py` looks for `plotter_config.json` **next to itself**, not next to
the student's script, so the calibration travels with the library.

---

## 3. The cable

- Use the **micro-USB socket on the printer's control board**, not the USB-A
  socket on the front (that one is for USB sticks only).
- **The cable must be a data cable.** Plenty of micro-USB cables are
  charge-only: the printer powers up and looks fine, but no serial port
  appears. If no port shows up, suspect the cable before anything else.
- Baud rate is 115200; the code sets this, nothing to configure.

### Confirming the printer is visible

From a terminal in the project folder:

```
python plotter.py --ports
```

On this laptop, with the printer on and connected:

```
COM5    Standard Serial over Bluetooth link (COM5)
COM8    Standard Serial over Bluetooth link (COM8)
COM7    Standard Serial over Bluetooth link (COM7)
COM3    Standard Serial over Bluetooth link (COM3)
COM10   USB Serial Device (COM10)   <-- Prusa
```

Windows lists every paired Bluetooth device as a COM port, so most of that
list is noise. The printer is found by its Prusa USB vendor id (`0x2C99`), not
by guessing, so the Bluetooth ports are ignored automatically.

For a full read-only check that opens the port but moves nothing:

```
python connect_test.py
```

---

## 4. A student's first run

1. Save their program in the folder with `plotter.py`.
2. Leave `LIVE = False` and press Run. The turtle window draws, and an SVG and
   a G-code file are saved. No printer needed.
3. When it looks right, change to `LIVE = True` and press Run again.

Their code does not change between the two - the only difference is the flag.

```python
from plotter import Plotter

LIVE = True

t = Plotter(live=LIVE)

t.forward(100)
t.left(90)

t.save_svg("mine.svg")
t.finish()
```

There are no pen heights and no port numbers in student code. Those live in
`plotter_config.json`.

---

## 5. First-run checklist

Before the first live run of a session:

- [ ] Paper taped down - 150 mm square, centred on the bed.
- [ ] Printer on, micro-USB cable in the control board.
- [ ] `python plotter.py --ports` shows a port marked `<-- Prusa`.
- [ ] **Nobody else is connected.** One at a time, see section 7.
- [ ] Pen fitted and in the holder, or deliberately removed for an air test.
- [ ] Hand near the power switch for the first run of the day.

Then expect, in order:

1. `Connecting to COM10 ...` - a second or two.
2. `Homing (this takes a moment)...` - **about 34 seconds**. This is normal and
   it is the longest wait in the whole system. Nothing appears to happen at
   first.
3. The head lifts and travels to the centre of the paper.
4. Drawing begins, in the same order the student's code runs.

A drawing of about 1000 mm of line takes roughly 40 seconds at the default
speed, plus the 34 second home. Budget about a minute and a half per run.

---

## 6. Safety

- **Heaters stay off.** The code turns them off at connect and the exported
  G-code files do the same. Nothing should ever get hot.
- **`G28` homes Z by probing the bed.** With a pen fitted this is the one real
  collision risk on this machine. Anything that homes asks first.
- **After homing, Z sits only 2 mm above the bed** and the head parks at
  X176 Y24 - not at the origin. The code always lifts Z before the first XY
  move. Do not reorder that.
- **The power switch is the emergency stop.** This firmware reports
  `EMERGENCY_PARSER:0`, which means an `M112` sent down the serial cable is
  queued behind whatever is already running and will *not* stop the machine
  immediately. Do not rely on it.

---

## 7. Only one person at a time

A serial port can be held open by exactly one program. If a second student
connects while the first is drawing, they get:

```
The printer's port (COM10) is already in use.
Usually that means someone else is connected to the printer, or a program
like PrusaSlicer or another Thonny window still has it open. Only one
person can use the printer at a time.
```

This is safe - the second program falls back to screen-only and keeps drawing.
It does not interfere with the run in progress.

Common causes, in order of likelihood:

1. Another student is genuinely drawing. Wait.
2. A previous program is still running. In Thonny, press the **Stop** button.
3. A Thonny window was closed without the program finishing. The port is
   released when that Python process exits - closing Thonny fully releases it.
4. PrusaSlicer or PrusaLink has the port open. Close it.

Calling `t.finish()` at the end of every program releases the port cleanly.
Make that a habit in the lesson.

---

## 8. Troubleshooting

| What the student sees | What it means | Fix |
|---|---|---|
| `pyserial is not installed` | Thonny is using an interpreter without pyserial | Tools > Manage packages > `pyserial`. Check the interpreter bottom-right. |
| `I can't find the printer` | No Prusa port | Printer off, wrong USB socket, or a charge-only cable. Try another cable. |
| `The printer's port is already in use` | Someone else is connected | See section 7. |
| `The printer stopped replying` | Port died mid-run | Power cycle the printer, replug USB, run again. |
| `a move went outside the paper and was clamped` | Drawing is bigger than the 150 mm paper | Not an error. Shrink the drawing, or ignore it - the pen stays on the paper. |
| Turtle window draws but the pen does not move | `LIVE` is still `False`, or connect failed and it fell back to screen-only | Read the messages in the shell; the fallback says so explicitly. |
| Nothing happens for ~30 seconds after Run | Normal - that is `G28` homing | Wait. |
| `ModuleNotFoundError: No module named 'plotter'` | The program is not saved next to `plotter.py` | Save the file into the same folder. |

### Everything still fails

Run these three in order and note what each says:

```
python plotter.py --ports        # is the port there at all?
python connect_test.py           # can we open it and talk? (moves nothing)
python motion_test.py            # prints a movement plan, sends nothing
```

`motion_test.py --yes` then runs a full home-and-corners test. **Remove the
pen before that one.**
