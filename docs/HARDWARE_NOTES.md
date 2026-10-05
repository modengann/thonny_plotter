# Hardware Notes - Prusa MINI as a pen plotter

Running log of every hardware finding: firmware versions, responses, quirks,
timings. Newest phase at the bottom.

## The machine
- Prusa MINI, Buddy firmware, micro-USB serial port on the control board,
  115200 baud.
- Bed 180 x 180 mm, centre (90, 90). Paper is a 150 mm square centred on the
  bed, so the paper runs 15 - 165 mm in both X and Y.
- Heaters stay off throughout. Pen up/down are Z moves.
- Spring-loaded pen holder mounted beside the extruder, so pen coordinates
  need a `pen_offset` (dx, dy) to become nozzle coordinates.
- **`G28` Z-homing can push the pen into the bed. This is the main collision
  risk on this build.**

## Phase 2 - connection (2026-09-25)

### Host-side findings (teacher's Windows 11 laptop)
- `python plotter.py --ports` with the printer unplugged lists four ports,
  all of them Bluetooth:

  ```
  COM5   Standard Serial over Bluetooth link (COM5)
  COM8   Standard Serial over Bluetooth link (COM8)
  COM7   Standard Serial over Bluetooth link (COM7)
  COM3   Standard Serial over Bluetooth link (COM3)
  ```

- **Quirk, and a real bug that was fixed before any hardware was touched:**
  Windows lists every paired Bluetooth device as a COM port. The original
  `find_prusa_port()` fell back to "any port whose name starts with com", so
  with the printer unplugged it would have picked `COM5` - a Bluetooth link -
  and tried to speak G-code to it. That would hang rather than fail cleanly.

  `find_prusa_port()` now requires, in order: the Prusa USB vendor id
  (`0x2C99`); or a `usbmodem` / `ttyACM` name; or a COM port that both has a
  USB vendor id and does not look like Bluetooth. With the printer unplugged
  it correctly returns `None`. This matters for students too - their laptops
  will have paired headsets and phones.

### Serial protocol handling written for Buddy
Buddy sends a lot that is not an answer. `_send()` now treats as chatter and
skips: `echo:`, `//` action comments, `start`, `Cap:`, `T:`/`B:` temperature
reports, `wait`, `Marlin`, `FIRMWARE_NAME:`, `buddy`. Only `ok` ends a
command. Specific behaviours:

- `ok` may arrive with trailing data (`ok T:24.1 /0.0`); still counts as done.
- `busy: processing` means the printer is alive and working, so it **resets**
  the timeout rather than counting towards it. Without this a long `G28` would
  look like a stall.
- `Error:` or `!!` raises with the offending command included.
- `M155 S0` is sent at connect to switch off automatic temperature reports and
  cut the chatter at the source.

All of this is covered by offline tests against a fake serial port
(`tests/test_serial_protocol.py`), including a 50-line `busy:` burst.

### Safety change
`connect()` used to call `G28` itself, so merely connecting would home the
printer - exactly the pen-into-bed collision. Motion is now split out:

- `connect()` - opens the port, `M115`, heaters off, `G21`, `G90`. **Moves
  nothing.** Safe with the pen fitted.
- `prepare()` - `G28`, lift to `pen_up_z`, travel to paper centre. **Moves the
  printer.** Must be called deliberately.

A test asserts `connect()` emits no `G28` and no `G1`.

### Timings
None yet - nothing has been sent. `connect()` currently allows a fixed 2.0 s
settle after opening the port, because the Buddy board reboots when the serial
port is opened. To be measured and tuned against the real machine.

### Connected (2026-09-25) - read-only handshake, nothing moved

Port: **COM10**, `USB Serial Device (COM10)`, vid **0x2C99**, 115200 baud.
The Prusa VID matched, so no guessing was needed. The four Bluetooth COM ports
were correctly ignored.

`M115` reply:

```
FIRMWARE_NAME:Prusa-Firmware-Buddy 6.4.0+11974 (Github)
SOURCE_CODE_URL:https://github.com/prusa3d/Prusa-Firmware-Buddy
PROTOCOL_VERSION:1.0  MACHINE_TYPE:Prusa-MINI  EXTRUDER_COUNT:1
UUID:cede2a2f-41a2-4748-9b12-c55c62f367ff
```

**Firmware: Buddy 6.4.0+11974.** Machine type confirmed as Prusa-MINI.

Capabilities reported (the ones that matter here):

| Cap | Value | Why it matters |
|---|---|---|
| `EMERGENCY_PARSER` | **0** | See the safety note below. |
| `AUTOREPORT_TEMP` | 1 | Supported, and `M155 S0` turns it off as intended. |
| `AUTOLEVEL` / `Z_PROBE` / `LEVELING_DATA` | 1 | Mesh bed levelling exists; `G29` is available but we do not want it for plotting. |
| `PROMPT_SUPPORT` | 1 | Firmware can raise dialogs on the printer's own screen. |
| `BINARY_FILE_TRANSFER` | 0 | Not needed. |

#### Safety note: `EMERGENCY_PARSER:0`
This build does **not** parse `M112` out of band. An emergency stop sent over
serial goes to the back of the command queue and will not take effect until
everything ahead of it has run. **The power switch is the only real emergency
stop on this machine.** Do not write any tool that implies a serial abort will
stop motion immediately.

#### Read-only queries

```
M105  temperatures   0.01s   T:23.06/0.00 B:23.20/0.00 A:33.15/0.00 @:0 B@:0
M114  position       0.00s   X:180.40 Y:-3.00 Z:0.00 E:0.00 Count X:18040 Y:-300 Z:0
```

- Heaters are off and cold (23 C nozzle, 23 C bed), as they should be. `A:33.15`
  is the board/ambient sensor.
- **`M114` before homing reports nonsense: X:180.40 (past the 180 mm bed edge)
  and Y:-3.00 (negative).** This is a stale count, not a real position. Never
  trust `M114` or send a relative move before `G28` has run.

#### Timings
- Opening the port plus the fixed 2.0 s settle: **2.0 s** total. The 2.0 s
  delay is enough - `M115` answered immediately afterwards on every run.
- `M105` and `M114` answer in **under 10 ms**. Buddy is quick to reply; the
  slow parts will be motion, not the protocol.

#### Quirk found and fixed: the chatter filter ate the replies
First run reported `(no reply to M115)` and no position from `M114`, which
looked like a silent printer. It was not. The chatter list included
`firmware_name`, `cap:`, `buddy` and `x:` - which is exactly what `M115` and
`M114` answer with, so the filter was discarding the answers.

The filter is now two tiers:
- `_NOISE` (`echo:`, `//`, `start`, `wait`, `adc`) - always dropped.
- `_TEMPERATURE` (`t:`, `b:`, `a:`) - dropped only when we are *not* collecting
  a reply, because `M105`'s answer looks identical to an autoreport.

Everything else is kept. Regression tests cover it, including that a
`FIRMWARE_NAME:` line survives.

Also confirmed: `M105`'s answer sometimes arrives appended to the `ok` line
(`ok T:24.1 /0.0`), which `_send()` handles.

## Phase 3 - scripted motion test (2026-09-25)

Run with **no pen fitted** ("writing in air"), via `python motion_test.py --yes`.
Completed with no errors and no intervention.

```
home all axes         G28                          33.63s
  position after homing: X:176.40 Y:24.10 Z:2.00
Z up to 10            G1 Z10.000 F600               0.84s
Z down to 5           G1 Z5.000 F600                0.54s
Z back to safe 10     G1 Z10.000 F600               0.54s
front left            G1 X15.000  Y15.000  F3000    3.29s
front right           G1 X165.000 Y15.000  F3000    3.06s
back right            G1 X165.000 Y165.000 F3000    3.06s
back left             G1 X15.000  Y165.000 F3000    3.06s
back to paper centre  G1 X90.000  Y90.000  F3000    2.19s
park                  G1 X0.000   Y170.000 F3000    2.47s
                                        whole run: 50.2s
```

All four paper corners were reachable. Final `M114` confirmed X:90.00 Y:90.00
Z:10.00, so commanded and actual positions agree after homing.

### Findings

**`G28` takes ~34 s.** That is the single slowest thing in the system and it
happens once per session. Budget for it in the lesson: a student pressing Run
waits a full half-minute before anything visible happens. Worth printing a
"homing, please wait" message (already done) and worth not homing more than
once per session.

**`G28` does not finish at the origin.** After homing, `M114` reports
**X:176.40 Y:24.10 Z:2.00** - Buddy parks the head at the right-hand side with
Z 2 mm off the bed, not at (0, 0, 0). Two consequences:
- Never assume the head is at origin after `G28`.
- **Z sits at only 2 mm after homing.** Anything fitted to the head that
  protrudes more than 2 mm below the nozzle will already be in contact with
  the bed at that point. When the pen goes on, lift Z *before* the first XY
  move. `prepare()` already does this.

**Feedrates are honoured exactly.** A 150 mm corner-to-corner move at F3000
(50 mm/s) took 3.06 s; 150/50 = 3.00 s. The 106 mm diagonal back to centre took
2.19 s against a predicted 2.12 s. Z at F600 (10 mm/s): the 5 mm move took
0.54 s against 0.50 s predicted.

**Per-command overhead is about 40 ms**, consistently, across both Z and XY
moves. That is the cost of `G1` + `M400` + the round trip. This matters for
lockstep drawing: every stroke segment costs its own travel time *plus* ~40 ms.
A drawing with 500 short segments spends ~20 s on protocol overhead alone.
Acceptable for classroom-sized drawings; something to watch if a student
generates a very dense curve (a `circle()` with many steps, for instance).

**First corner move was slightly slower** (3.29 s vs 3.06 s) - acceleration
from a standstill. Not significant.

### Still unknown, for Phase 4
- `pen_down_z` and `pen_up_z`: not measurable without the pen fitted.
- `pen_offset`: the pen holder sits beside the extruder, so the offset is
  unknown until the pen is on. Everything above used offset (0, 0).

## Live pipeline test - Thonny to printer (2026-09-25)

Pen **not** fitted; drawing in air with `pen_up_z` 15, `pen_down_z` 10 from
`plotter_config.json`. Run under **Thonny's own bundled Python**
(`AppData/Local/Programs/Thonny/python.exe`), not a system Python, so this
tests the interpreter the students will actually use.

`hello_shapes.py` with `LIVE = True` completed with no errors in 39.8 s.
Re-run instrumented via `live_timing_test.py --yes`:

```
connect (port + handshake)             2.11 s
prepare (home + lift + centre)        16.65 s
DRAWING                               19.06 s
finish (park + motors off)             2.77 s
                         wall clock   40.59 s

phase                      count   seconds
G28 home                       1     13.11
G1 Z (pen up/down)             9      0.01
G1 XY drawing (F1500)         16      0.02
G1 XY travel (F3000)           6      0.01
M400 waits                    30     25.33
```

### Finding: `G1` returns instantly, `M400` carries all the time

This looked alarming at first (a drawing that should take ~16 s appearing to
take ~6 s) and it is worth writing down clearly, because it is the mechanism
the whole design depends on.

**Buddy answers `ok` to a `G1` as soon as the move is accepted into the motion
planner, not when the move finishes.** All 31 `G1` commands together took
**0.04 s** to acknowledge. The real motion time - **25.33 s** - is spent inside
the 30 `M400` calls.

So `M400` is not a nicety, it *is* the lockstep. Remove it and the program
would race to the end while the head was still moving, and with a pen fitted
the drawing would lag behind the code and finish long after `finish()` ran.
**Never drop the `M400` after a move**, and never "optimise" it away to make
drawings faster.

The earlier per-command figure of ~40 ms from Phase 3 was the `M400` round
trip, not the `G1`.

### Finding: `G28` duration varies a lot depending on whether it is already homed

- **Cold / unhomed: ~34 s** (Phase 3 motion test, measured 33.63 s).
- **Already homed: ~13 s** (measured 13.11 s here, straight after a previous
  run).

This explains the first live run finishing in 39.8 s rather than the ~55 s
predicted from the Phase 3 number. It is not a fault. Practical effect: the
first run of a lesson is the slow one; subsequent runs are about 20 s quicker.

### Timing model for the classroom

Drawing time predicted from the G-code is reliable:

- drawn line at F1500 = 25 mm/s
- travel at F3000 = 50 mm/s
- pen up/down 5 mm at F600 = 0.5 s each
- about 40 ms per command on top

`hello_shapes.py` is 280 mm of drawn line plus travels and 8 pen moves;
predicted ~17 s, measured 19.06 s. The remainder is acceleration on short
moves. Good enough to estimate any student drawing from its G-code.

## AX4 (IKRANBIRD, GRBL) - first contact, 2026-10-04

Read-only check with `grbl_connect_test.py COM12`. Nothing moved.

- Port **COM12, USB-SERIAL CH340 (vid 0x1A86 pid 0x7523)**, 115200 baud.
  `find_prusa_port()` would also pick it (USB vid, not Bluetooth), by luck.
- Firmware **`Grbl 0.9i`**. The banner arrives ~1.5 s after the port opens
  (opening resets the board); our first command was swallowed by the reset.
  Any GRBL backend must wait for the banner before sending.
- `$I` gave no build-info line, only the banner.
- Status: `<Idle,MPos:0,0,0,WPos:0,0,0>` - not in alarm, no unlock needed.
- **`$22=0` homing off, `$21=0` hard limits off, `$20=0` soft limits off.**
  No reference point: machine 0,0 is wherever the head sits at power-on /
  reset. Nothing stops a move past the frame - the backend must clamp.
- `$100/$101=80` steps/mm, `$110/$111=6000` mm/min max, `$120/$121=600`
  mm/s^2, `$130=300` x travel, `$131=210` y travel (A4 landscape).
- No `$30`/`$31` (spindle range is a GRBL 1.1 setting), so the servo S
  values for pen up/down are compiled in and must be found by testing.

### AX4 pen servo (servo_test.py, 2026-10-04)
- `M3 S<n>` drives the servo; the firmware acks every value 0-1000.
- **`M5` and `S0` = pen up** (same position). Board reset also gives `M5`,
  so a crash or reset leaves the pen up - deliberate horn orientation.
- Pen travels S0 -> ~S50; above ~S50 nothing further moves (carriage at
  the bottom of its guide). No buzzing anywhere in 0-1000.
- Proposed: pen up `M5`, pen down `M3 S60` (horn clear, pen floats).
  Pen tip should be set in the clamp so it touches paper with the carriage
  2-3 mm above bottom of travel. Not yet confirmed with a touch test.
- servo_test.py beeps per step and is best launched in its own console
  window so the teacher can see the S value live.
- After adjusting the pen in its clamp, a 50-110 sweep showed the pen
  stops moving at **S70**. Updated proposal: pen up `M5`, **pen down
  `M3 S80`**. (Supersedes the S60 figure above.)
- Every port open resets the board (pen pops up to M5). Opening with
  DTR/RTS low did not prevent it on this CH340 board.
- **Final pen setup (confirmed):** pen re-clamped so the tip touches the
  paper at S60; by S70 the horn has left the carriage and the pen floats on
  the paper under its own weight. **Pen up `M5`, pen down `M3 S80`.**
  The first `M5` after connecting never moves anything - the port-open reset
  already put the servo there.

### AX4 first axis move (grbl_motion_test.py --yes, 2026-10-04)
- Directions (teacher jogged in Candle): **+X = right, +Y = up/away**.
  Matches turtle; no axis inversion needed.
- Pen up, from wherever the head sat at reset: X+20, Y+20, back to 0,0 at
  F1000. No errors; status Idle and reported position exact after each move.
- **Lockstep confirmed: `G4 P0` is GRBL's `M400`.** `G1` is acked in 0.00 s
  (queued); the `G4 P0` ok only comes back when motion finishes.
  20 mm took 1.75 s, the 28.3 mm diagonal 2.46 s (17 mm/s + accel + ~0.3 s
  round trip incl. the status query).
- **NOT DONE: mm calibration.** Nobody has measured whether 20 commanded mm
  is 20 real mm ($100/$101 = 80 steps/mm, factory value). Teacher will do it
  later: draw a long line (e.g. 200 mm), measure, correct $100/$101.

### First pen drawing on the AX4 (write_name.py --yes, 2026-10-04)
- "Kim Sejoung", single-stroke letters, ~101 x 22 mm, 19 strokes.
  Pen up M5 / down M3 S80, draw F1500, travel F3000, 0.3 s servo wait.
- Completed with no errors in **39.6 s**; head returned to start.
- Result on paper: **worked** (teacher confirmed).
- "Sophia Moden" at baseline 45 mm (one line up): first run **drew in air**
  with the same M3 S80. Likely cause: tiny float margin (touch at S60,
  carriage bottoms at S70), so a slightly lower paper/bed spot higher up the
  page leaves the tip hanging. Fix if it recurs: re-clamp the pen lower so it
  touches at ~S40-50. Rerun completed (43.9 s); paper result not reported.
- "molly moden" at the bottom line: 17 strokes, 38.1 s, no errors.
- write_name.py glyphs: full A-Z and a-z, space, Hangeul 김 세 정 사 랑 해 요. No digits or punctuation.
- Hangeul: added syllable blocks 김 세 정 사 랑 해 요 (hand-built from jamo, 10x10
  units). "김세정" plotted: 14 strokes, 25.7 s, no errors.
- Gotcha: Candle grabs the port whenever it is connected (used for moving
  the head). Disconnect it before every script run or you get
  "Access is denied" on COM13.
- "사랑해요" plotted: 18 strokes, 33.2 s, no errors.
- "bruce moden" plotted: 17 strokes, 38.8 s, no errors.
- "bruce loves hockey" plotted: 23 strokes, 54.9 s, no errors (172 mm wide).
- draw_turtle.py: turtle animal, 86 x 70 mm centred on the head position, 15 strokes, 57.0 s, no errors. First drawing using negative coordinates (origin at paper centre) - fine, no soft limits.
