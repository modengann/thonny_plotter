# AX4 dashboard and turtle backend - design

Date: 2026-10-04. Status: approved in conversation, awaiting written review.

## Goal

Let the teacher plot students' ordinary Python turtle programs on the
IKRANBIRD AX4 pen plotter, from a desktop dashboard that someone in a future
year can set up and run without help.

Success means:

- A student writes plain `import turtle` code in Thonny, emails the `.py`
  file, and the teacher plots it from the dashboard with no edits to the
  student's code and nothing installed on the student's laptop.
- The teacher can set up the pen, set the origin, calibrate distances, and
  stop a plot from the dashboard, without Candle and without typing G-code.
- The existing Prusa MINI path keeps working, and its 45 tests keep passing.

## Decisions (from the teacher)

| Topic | Decision |
|---|---|
| How student code arrives | Emailed `.py` file. No upload server, no network, no GitHub. |
| Who uses the dashboard | Teacher only, on the laptop wired to the AX4. |
| Dashboard form | Tkinter desktop window (stdlib + pyserial only, runs from Thonny). |
| Paper | Always US Letter, landscape. |
| Scale | 100% = 0.25 mm per turtle step; adjustable percentage. |
| Setup | Guided, plain-language pen setup and distance calibration. |
| Calibration | Not done yet; must stay visible until it is. |

## Known hardware facts (see docs/HARDWARE_NOTES.md)

- AX4: CoreXY, GRBL 0.9i, CH340 USB-serial (VID 0x1A86), 115200 baud.
- Opening the port resets the board; the banner `Grbl 0.9i ['$' for help]`
  arrives about 1.5 s later. Commands sent before it are lost.
- No homing, no limit switches, no soft limits. 0,0 is wherever the head is.
- Travel: X 300 mm, Y 210 mm. Steps/mm 80 (factory, not calibrated).
- Pen: up `M5` (also the state after any reset), touch `M3 S60`,
  down `M3 S80`.
- `G1` is acknowledged when queued. `G4 P0` returns `ok` only after motion
  finishes: it is the lockstep.
- +X is right, +Y is away from the teacher (up the page). Matches turtle.
- Candle holds the port while connected; nothing else can open it.

## Architecture

Three units, each usable and testable alone.

```
student.py --> run_turtle.py (subprocess) --> strokes JSON (mm)
                                                   |
                                         dashboard.py (Tkinter)
                                         preview, scale, checklist
                                                   |
                                     plotter.py: GrblBackend --> AX4
```

### 1. Backends in `plotter.py`

A small interface that the `Plotter` turtle and the dashboard both use:

| Method | Meaning |
|---|---|
| `connect(port=None)` | Open the port, handshake. Moves nothing. |
| `prepare()` | Make the machine ready to draw (MINI: home; GRBL: unlock if needed, pen up). |
| `pen(down)` | Raise or lower the pen; no-op if already there. Waits for the servo/Z. |
| `move(x, y, feed)` | Queue one straight move to (x, y) mm in paper coordinates. |
| `wait()` | Block until all queued motion has finished. |
| `pause()` / `resume()` | Feed hold and resume (GRBL only; MINI raises "not supported"). |
| `stop()` | Stop as fast as the firmware allows. |
| `finish()` | Pen up, release, close the port. |

- **`MiniBackend`**: the current Prusa code moved out of `Plotter`
  unchanged in behaviour: `G28`, Z pen moves, `M400` lockstep, Buddy chatter
  filtering, heaters off, bed-centre coordinates, `pen_offset`.
- **`GrblBackend`**: for the AX4.
  - `connect`: open at 115200, wait for the `Grbl` banner (timeout 5 s),
    send `G21`, `G90`. Record the firmware string.
  - `pen`: `M5` / `M3 S<pen_down_s>`, then `G4 P<servo_wait>` (0.3 s).
    Always `G4 P0` before a pen change so the pen never drops mid-travel.
  - `move`: `G1 X.. Y.. F..` in paper coordinates (origin at paper centre).
    Refuses (raises) any point outside the paper's usable area. Never clamps.
  - `wait`: `G4 P0`.
  - `pause` / `resume`: realtime `!` / `~`.
  - `stop`: realtime `!`, then Ctrl-X (`0x18`) soft reset. After reset the
    pen is up (`M5` is the reset state). If GRBL reports `ALARM`, send `$X`.
    The origin is then considered lost.
  - `set_origin()`: `G92 X0 Y0` at the current head position.
  - `jog(dx, dy)`: relative move with pen up, used only by the dashboard.
  - Reply handling: `ok` ends a command; `error:N` raises a `PlotterError`
    naming the command; `ALARM` raises; `[...]` and `<...>` lines are status
    and are returned when asked for, otherwise ignored.
- Backend choice comes from `plotter_config.json` (`"backend": "grbl"` or
  `"mini"`), default `"mini"` so nothing changes for the existing setup.
- Student code that uses `Plotter(live=True)` works with either backend.

### 2. `run_turtle.py` - runs a student file

- Runs as a separate process: `python run_turtle.py student.py`.
  Timeout 20 s, enforced by the dashboard.
- Before running the student file it replaces `turtle.Turtle` (and
  `turtle.Pen`, `turtle.RawTurtle`) with a recording turtle, so that:
  - `t = turtle.Turtle()` records,
  - module-level calls such as `turtle.forward(100)` record (they use the
    module's default turtle, which is created from `turtle.Turtle`),
  - several turtles record into one shared list, in the order the code ran.
- `turtle.done`, `turtle.mainloop`, `turtle.exitonclick`,
  `Screen().mainloop` and `Screen().exitonclick` become no-ops.
- Drawing runs with `tracer(0)` and the window hidden.
- `input()` raises a clear error (stdin is closed).
- Output: one JSON object on stdout:
  `{"strokes": [[[x, y], ...], ...], "warnings": [...], "error": null | {...}}`
  Coordinates are in turtle units (not mm); the dashboard applies scale.
  On an exception, `error` holds the type, message and the student's line
  number, and `strokes` holds what was drawn before it.
- Warnings, collected once each: fill used (outline only), `write()` used
  (text not drawn), `dot()`/`stamp()` used (not drawn), more than one pen
  colour (one pen; all lines the same colour).

### 3. `dashboard.py` - the teacher's window

Logic lives in `dashboard_logic.py` (no Tkinter imports) so it can be
tested; `dashboard.py` is the window.

**Layout (one window):**

- Top: setup checklist and status line.
- Left: controls - Connect, jog pad (1 / 10 mm steps), Set origin here,
  Pen up / Pen down, Change pen, Pen setup..., Calibrate distances...
- Centre: preview canvas showing the Letter sheet, the usable area, and the
  drawing. Parts outside the usable area are drawn red.
- Right: the student's code (read-only), file name, stroke count, size in
  mm, estimated time, warnings, errors.
- Bottom: Open student file..., Scale % box, Fit to paper, Reset 100%,
  Plot, Pause/Resume, STOP, Save SVG..., progress bar.

**Setup checklist** (shown on start; Plot disabled until 1-3 are ticked):

| Item | Remembered? | Blocks Plot |
|---|---|---|
| 1. Connected to AX4 | no, every session | yes |
| 2. Pen set up | yes (config), re-run button | yes, first time only |
| 3. Origin set (head at paper centre) | no, every session; cleared on reconnect, STOP or error | yes |
| 4. Distances calibrated | yes (config, with date) | no - yellow "NOT CALIBRATED" banner until done |

**Scale and paper:**

- Letter landscape 279.4 x 215.9 mm, 10 mm margin: usable 259.4 x 195.9 mm,
  i.e. X within +/-129.7 mm and Y within +/-97.95 mm of the origin.
- The sheet (215.9 mm) is taller than the AX4's Y travel (210 mm). The
  usable height (195.9 mm) fits only if the sheet is centred in the travel,
  leaving about 7 mm spare at each end. The origin step says: "Place the
  sheet centred on the plotter bed, then jog to the centre of the sheet."
- mm = turtle units x 0.25 x (scale% / 100), about the origin.
- Fit to paper: largest scale% at which every point is inside the usable
  area, rounded down to a whole percent.
- If any point is outside: red in the preview, Plot disabled, message
  "Drawing doesn't fit - use Fit to paper or a smaller scale."
- Time estimate from the stroke lengths: draw F1500, travel F3000, 0.3 s per
  pen change, plus 0.05 s per segment.

**Plotting:**

- Runs in a worker thread; the window stays responsive. Each stroke:
  travel, `wait`, pen down, segments, `wait`, pen up. Progress per stroke.
- Pause/Resume and STOP talk to the backend directly from the UI thread
  (realtime bytes), not through the worker queue.
- After a plot: pen up, head returns to the origin.
- Closing the window during a plot asks "Stop the plot?" first.

**Pen setup wizard** (plain language, one step per screen):

1. "Pen is lifted. Loosen the clamp and take the pen out." (sends `M5`)
2. "Put a sheet of paper under the pen holder. Click *Lower to touch
   position*." (sends `M3 S<touch_s>`, default 60)
3. "Slide the pen down until the tip just touches the paper, then tighten
   the clamp. The pen should rest on the paper, not on the bottom of its
   holder."
4. "Test": draws a 40 mm zigzag near the origin, lifts. Asks what the
   teacher sees:
   - Solid lines -> save, tick checklist item 2.
   - Faint, gaps or nothing -> back to step 3, set the pen slightly lower.
   - Lines joining the zigzags -> the pen is not lifting; check the servo
     horn (help text).
5. Advanced (collapsed): sliders for touch S and down S with live servo
   movement; saved to config.

The test needs an origin, so step 4 asks the teacher to set one first if it
is not set.

**Change pen:** pen up, move head to the front centre of the usable area,
message "Swap the pen, then click Done"; head returns to the origin.

**Distance calibration wizard:**

1. "Put down a fresh sheet." Requires origin set and pen set up.
2. Draws an L: 150 mm along X and 150 mm along Y from (-75, -75), with a
   5 mm tick across each end.
3. "Measure each line between the ticks with a ruler." Two number boxes
   (mm), checked to be between 140 and 160.
4. New steps/mm = current x 150 / measured. Because the AX4 is CoreXY and
   GRBL assumes the A and B motors share one steps/mm (to be confirmed on
   hardware before release), the wizard applies the **average** of the
   two results to both `$100` and `$101`, and says so if X and Y differed
   by more than 1%.
5. Shows old -> new, Apply writes `$100=` / `$101=` (stored in the AX4's
   EEPROM), records the date in config, clears the banner.
6. Offers "Draw again to check".

## Configuration (`plotter_config.json`)

New keys, all optional with defaults:

```json
{
  "backend": "grbl",
  "paper": "letter",
  "margin_mm": 10,
  "pen_touch_s": 60,
  "pen_down_s": 80,
  "servo_wait_s": 0.3,
  "draw_feed": 1500,
  "travel_feed": 3000,
  "pen_setup_done": "2026-10-04",
  "calibrated": null
}
```

Existing MINI keys are unchanged. The air-test Z values currently in the
file stay until the MINI is re-calibrated.

## Error handling

**Student file:**

| Problem | Shown |
|---|---|
| Syntax error / exception | "Line N: <Type>: <message>", partial drawing greyed |
| Over 20 s | "The program took too long - is there a loop that never ends?" |
| `input()` | "This program asks for keyboard input, which the plotter can't do." |
| fill / write / dot / stamp / colours | Plots anyway, with the matching warning |
| Click or key handlers | The drawing made before mainloop is plotted; handlers never run |

**Hardware:**

| Problem | Behaviour |
|---|---|
| Port busy | "Another program has the plotter - probably Candle. Disconnect it there." |
| No CH340 port | "Can't find the plotter. Is it plugged in and switched on?" |
| No banner in 5 s | "The plotter didn't answer. Unplug and replug the USB cable." |
| `error:N` | Stop the plot, show the command and the error. |
| `ALARM` | Stop, unlock with `$X`, origin cleared. |
| Port lost mid-plot | Stop, "Connection lost. Lift the pen by hand if it is down, reconnect, set the origin again." Origin and connection unticked. |
| STOP | `!` then Ctrl-X; pen up; `$X` if alarmed; origin cleared. |

Nothing moves except in response to a button the teacher pressed.

## Testing

**Automated, offline (stdlib `unittest`, no hardware):**

- `tests/test_grbl_backend.py`: a `FakeGrbl` serial object replays banner,
  `ok`, `error:N`, `ALARM`, status lines. Covers: waits for banner; G21/G90
  at connect; pen sequences (`G4 P0` before pen change, servo dwell);
  out-of-paper move raises and sends nothing; stop sends `!` then `0x18`;
  error and alarm raise `PlotterError`.
- `tests/test_run_turtle.py`: sample files under `tests/samples/` - good
  object style, module-level style, two turtles (order kept), syntax error,
  NameError partway (partial strokes kept), infinite loop (killed), `input()`,
  fill/write warnings.
- `tests/test_dashboard_logic.py`: mm conversion, fit-to-paper, out-of-paper
  detection, time estimate, checklist rules, calibration arithmetic.
- The existing 45 tests pass unchanged (MiniBackend refactor).

**Manual, dashboard window:** a short checklist in `docs/SETUP.md` run by
hand (open file, scale, fit, preview colours, buttons enable/disable).

**On the AX4, teacher present, in order:**

1. Connect (read-only).
2. Pen setup wizard.
3. Set origin, plot a small sample file.
4. Press STOP mid-plot; confirm pen lifts, alarm handled, origin cleared.
   Confirm GRBL 0.9's behaviour after Ctrl-X matches this design.
5. Distance calibration wizard; confirm CoreXY `$100`/`$101` handling.

## Out of scope

- Network upload, student queue, accounts.
- Multiple pen colours or pen-change pauses.
- `turtle.write()` via the stroke font (possible later).
- Class gallery of saved SVGs.
- Moving `write_name.py`, `draw_turtle.py` into the dashboard.
- Folder reorganisation into `student/`, `teacher/`, `docs/` (end of
  project, as already agreed).

## Open items to confirm on hardware

- GRBL 0.9 state after Ctrl-X during motion (ALARM or Idle).
- CoreXY: whether `$100` and `$101` must be equal on this firmware.
- Whether `G4 P0` also guards `M3`/`M5` ordering on this firmware (design
  sends it anyway).
