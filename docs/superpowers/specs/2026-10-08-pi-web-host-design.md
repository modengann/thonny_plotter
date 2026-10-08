# Raspberry Pi web host for the AX4 dashboard - design

Date: 2026-10-08. Status: approved in conversation (option A), awaiting
written review.

## Goal

Move the AX4 dashboard off the teacher's laptop onto a Raspberry Pi wired to
the plotter, so long plots do not depend on a laptop staying awake and
connected, and students can upload their own `.py` files from a browser.

Success means:

- The Pi boots straight into a working dashboard with no keyboard or monitor.
- Anyone on the school network opens `http://<pi-ip>:6080/` and sees and
  drives the same dashboard that runs on the laptop today.
- A student opens `http://<pi-ip>:8000/`, uploads a turtle program, and it
  appears in the dashboard's Open dialog. Files that are not plain turtle
  programs are rejected with a plain-language reason.
- A plot keeps running when every browser is closed.
- The laptop path (`python dashboard.py` on Windows) keeps working, and all
  existing tests keep passing.

## Decisions (from the teacher)

| Topic | Decision |
|---|---|
| Approach | A: stream the existing Tk dashboard to the browser (Xvfb + x11vnc + noVNC). No HTML rewrite. |
| Display | Same dashboard as the laptop. Virtual display is fine. |
| Who can control | Everyone who connects (open access). Tighten later only if it becomes a problem. |
| Concurrent users | Shared screen and mouse; many viewers allowed (`x11vnc -shared`). |
| Misuse risk | Low (small class, physically present). A static code check plus a limited user is enough; no real sandbox. |
| Machine readiness | Existing checklist is enough; no per-plot "paper loaded" gate. |
| Physical STOP | Teacher will wire a button; software hook included. |
| Network | Reused OctoPrint Pi with a reserved IP; assume students can reach it. |
| Testing | Pi stack built and checked at home; only the AX4 connection is left for school. |

## Architecture

```
 browser :6080 ──> websockify/noVNC ──> x11vnc ──> Xvfb :1 ──> openbox
                                                        └──> dashboard.py ──USB──> AX4
 browser :8000 ──> upload_server.py (Flask) ──> uploads/*.py <── Open dialog
                                                                   │
                         dashboard runs  sudo -u plotstudent run_turtle.py
```

The dashboard process owns the serial port for its whole life. Browsers only
look at it, so closing them has no effect on a plot.

## Components

### 1. `code_check.py` (new, stdlib only)

`check(source) -> list of str`. Empty list means OK. Each message is plain
language and starts with the line number, e.g.
`Line 3: plotter programs can only import turtle, math, random, time, colorsys.`

Parses with `ast` (never executes). Rules:

- Syntax error: one message with the line, so the student hears about it
  before anything runs.
- Imports: only `turtle`, `math`, `random`, `time`, `colorsys`
  (both `import x` and `from x import ...`).
- Banned names when called or referenced: `open`, `exec`, `eval`, `compile`,
  `__import__`, `getattr`, `setattr`, `delattr`, `globals`, `locals`, `vars`,
  `breakpoint`, `input` is allowed (run_turtle already handles it).
- Banned attributes: any name starting with `_` (blocks dunder escapes and
  private turtle internals), plus `getcanvas`, `cv`, `tk` (the Tk canvas
  gives a route to Tcl `exec`).
- Banned names (identifiers): any starting with `__`.

This is a guard against accidents and casual mischief, not a sandbox. The
limited user and the 20 s timeout are the second layer.

### 2. `upload_server.py` (new, Flask)

Port 8000 (configurable with `--port`). One page, plain HTML from an inline
template, readable on a phone:

- Name box + file picker + Upload button.
- On upload: name cleaned to letters, digits, `-`, `_` (max 30 chars, empty
  becomes `student`); file must end `.py`, be under 100 KB, and decode as
  UTF-8. Then `code_check.check()`. If it passes, saved as
  `uploads/<name>_<YYYYMMDD-HHMMSS>.py`; otherwise not saved and the
  problems are shown.
- List of the 20 newest uploads (name and time).
- A large link "Open the plotter dashboard" to `http://<same host>:6080/vnc.html?autoconnect=1&resize=scale`.

`uploads/` lives in the project folder, created on start, git-ignored.
No deletion from the web page (teacher clears the folder by hand if needed).

### 3. Dashboard changes (small)

- Open dialog `initialdir` is `uploads/` when it exists.
- `load_file` runs `code_check.check()` first; problems are shown in the
  existing error area and the program is not run.
- New optional config key `run_as` (default absent). When set,
  `run_student` prefixes the command with `sudo -n -u <run_as>`. Absent on
  Windows, so the laptop path is unchanged.
- New optional config keys `stop_pin` (BCM number, default absent). When set
  and `gpiozero` imports, a button on that pin (to ground, internal pull-up)
  triggers the same action as the on-screen STOP, via `root.after` so it runs
  on the Tk thread.
- Window opens maximised to the virtual screen when `--kiosk` is passed
  (the Pi service passes it).

### 4. `pi/` folder (new)

- `setup.sh` - run once with sudo on Raspberry Pi OS (Bookworm, Lite or
  Desktop). Installs `xvfb openbox x11vnc novnc websockify python3-tk
  python3-serial python3-flask python3-gpiozero`; creates the `plotstudent`
  user (no login shell, no `dialout`); adds a sudoers drop-in letting the
  service user run `/usr/bin/python3` as `plotstudent` without a password;
  adds the service user to `dialout`; installs and enables the services;
  writes `run_as` and leaves other config untouched.
- systemd units (all `Restart=on-failure`, start on boot):
  - `plotter-display.service` - Xvfb `:1` at 1280x800, openbox,
    `xhost +SI:localuser:plotstudent`, then `python3 dashboard.py --kiosk`.
  - `plotter-vnc.service` - `x11vnc -display :1 -shared -forever -nopw`
    on localhost only.
  - `plotter-novnc.service` - websockify on 6080 serving the noVNC files.
  - `plotter-upload.service` - `python3 upload_server.py`.
- Disables OctoPrint's service if present (it would grab the USB port).

### 5. `docs/PI_SETUP.md` (new)

Plain steps: flash or reuse the Pi, copy the project, run `setup.sh`, the two
URLs, how to restart, what to do if the screen looks wrong, wiring the STOP
button (pin, ground), and the gotcha below.

## Gotchas

- **Restarting the dashboard resets the AX4.** Opening the CH340 port resets
  GRBL, which clears the origin. Closing the dashboard window in the browser
  makes systemd restart it. The checklist already blocks Plot until the origin
  is set again; PI_SETUP.md says so.
- **Shared mouse.** Two people clicking at once will interfere. Social rule,
  not code.
- **Tk file dialog on Linux** is the plain Tk one, not the native dialog. It
  works; it looks dated.
- **OctoPrint** must be off or uninstalled, or it will hold the serial port.

## Error handling

- Upload rejected: shown on the page, nothing saved.
- Code check fails in the dashboard: shown in the dashboard, program not run.
- `sudo -n` fails (setup missing): `run_student` already turns a non-JSON
  result into a readable error; the message names the cause.
- `gpiozero` missing or no `stop_pin`: hook silently off.
- A service crashes: systemd restarts it.

## Testing

At home, on Windows (automated, offline):

- `tests/test_code_check.py` - accepted programs (all files in
  `tests/samples/`, `from turtle import *`, math/random use); rejected:
  `import os`, `from subprocess import run`, `open(...)`, `eval`,
  `__import__`, `().__class__`, `t.getscreen().getcanvas()`, syntax error
  with line number.
- `tests/test_upload_server.py` - Flask test client: good upload saved with
  cleaned name; bad code not saved and message shown; non-.py and oversize
  rejected; list shows newest first.
- `tests/test_dashboard_logic.py` - `run_as` builds the `sudo -n -u` prefix;
  absent gives the old command.
- `tests/test_dashboard_smoke.py` - `load_file` on a rejected file shows the
  problem and does not call the runner; Open uses `uploads/`.
- STOP hook: tested with a fake button object (no GPIO needed).

At home, on the Pi (manual checklist, no AX4): services up after reboot;
dashboard visible at :6080 from a laptop and a phone; two browsers at once;
upload at :8000 appears in the Open dialog; a sample program previews; a
rejected program is refused; Connect fails with the friendly "not found"
message; STOP button (if wired) logs a press.

At school (AX4): Connect, pen setup, origin, plot a sample, STOP mid-plot,
close all browsers mid-plot and confirm it finishes.

## Out of scope

HTML rewrite of the dashboard (option B), logins/roles, a print queue,
per-plot paper confirmation, HTTPS, deleting uploads from the web page.
