# Raspberry Pi web host Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run the existing AX4 Tk dashboard on a Raspberry Pi, viewable and drivable from any browser through noVNC, plus a Flask page where students upload turtle programs that are statically checked before they can run.

**Architecture:** The unchanged `dashboard.py` runs on a virtual X display (Xvfb :1) on the Pi; x11vnc + websockify/noVNC serve it on port 6080. A separate Flask app (`upload_server.py`, port 8000) checks and saves uploads into `uploads/`, which the dashboard's Open dialog starts in. Student programs are checked by `code_check.py` and run as a limited `plotstudent` user.

**Tech Stack:** Python 3.9+ (3.10 on the laptop, 3.11 on Raspberry Pi OS Bookworm), Tkinter, pyserial, Flask (upload page only), gpiozero (optional), systemd, Xvfb, openbox, x11vnc, noVNC/websockify.

**Spec:** `docs/superpowers/specs/2026-10-08-pi-web-host-design.md`

## Global Constraints

- The laptop path must keep working: `python dashboard.py` on Windows with stdlib + pyserial only. Flask is imported only by `upload_server.py`; gpiozero only inside `stop_button.py`, guarded.
- Code must run on Python 3.9+ (no `match`, no `X | Y` type hints).
- Tests are stdlib `unittest`, one file per module, runnable as `python tests/test_<name>.py` from the project root. All existing tests keep passing.
- Ports: dashboard (noVNC) **6080**, upload page **8000**.
- Allowed student imports, exactly: `turtle`, `math`, `random`, `time`, `colorsys`.
- Upload limit **100 KB**; names cleaned to letters/digits (any script, incl. Hangeul), `-`, `_`, max **30** chars, empty becomes `student`.
- Files in `pi/` must have LF line endings.
- `uploads/` is git-ignored. **Never commit `plotter_config.json`** (it is the teacher's live config; it has local edits). Stage files by name, never `git commit -a`.
- Plain language in every user-facing message; no emojis.
- Commit message trailer: `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`

## Review Focus

1. A student uses the standard `if __name__ == "__main__": main()` guard — must be accepted, not flagged as a dunder. (Task 1 test `test_main_guard_is_allowed`.)
2. A student types a Korean name (the class uses Hangeul) — must be kept, not collapsed to `student`. (Task 5 test `test_hangeul_kept`.)
3. Two uploads with the same name in the same second — the second must not overwrite the first. (Task 5 test `test_same_second_does_not_overwrite`.)
4. A file saved with a UTF-8 BOM (Notepad) — must be accepted and saved without the BOM. (Task 5 test `test_bom_file_is_accepted`.)
5. An oversized upload — must get a friendly "too big" page, not a raw 413. (Task 5 test `test_too_big_has_a_friendly_message`.)

---

### Task 1: Static code check (`code_check.py`)

**Files:**
- Create: `code_check.py`
- Test: `tests/test_code_check.py`

**Interfaces:**
- Produces: `code_check.check(source: str) -> list[str]` — empty list means OK; each string starts `"Line <n>: "`, sorted by line. `code_check.ALLOWED_MODULES` (tuple of str).

- [ ] **Step 1: Write the failing tests**

`tests/test_code_check.py`:

```python
"""
Tests for code_check.py -- the static check run on every student program
before it is saved or run.  No subprocess, nothing is executed.

    python tests/test_code_check.py
"""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from code_check import check

SAMPLES = os.path.join(HERE, "samples")


class TestAccepted(unittest.TestCase):

    def test_every_sample_but_the_syntax_error_passes(self):
        for name in sorted(os.listdir(SAMPLES)):
            if not name.endswith(".py") or name == "syntax_error.py":
                continue
            with open(os.path.join(SAMPLES, name), encoding="utf-8") as f:
                self.assertEqual(check(f.read()), [], name)

    def test_allowed_modules(self):
        src = ("import turtle\nimport math, random\nfrom time import sleep\n"
               "import colorsys as c\nfrom turtle import *\nimport turtle as t\n")
        self.assertEqual(check(src), [])

    def test_main_guard_is_allowed(self):
        src = ("import turtle\n\ndef main():\n    turtle.forward(10)\n\n"
               "if __name__ == '__main__':\n    main()\n")
        self.assertEqual(check(src), [])

    def test_input_and_private_looking_variables_are_allowed(self):
        src = "n = int(input('How many? '))\n_size = 5\n"
        self.assertEqual(check(src), [])


class TestRejected(unittest.TestCase):

    def assertRejected(self, src, line, word):
        problems = check(src)
        self.assertTrue(problems, src)
        self.assertTrue(problems[0].startswith("Line %d: " % line), problems)
        self.assertIn(word, problems[0])

    def test_other_imports(self):
        self.assertRejected("import os\n", 1, "os")
        self.assertRejected("import turtle\nfrom subprocess import run\n", 2,
                            "subprocess")
        self.assertRejected("import os.path\n", 1, "os")
        self.assertRejected("from . import thing\n", 1, "import")

    def test_import_message_lists_what_is_allowed(self):
        self.assertIn("turtle, math, random, time, colorsys", check("import os\n")[0])

    def test_dangerous_builtins(self):
        self.assertRejected("f = open('x.txt')\n", 1, "open")
        self.assertRejected("eval('1+1')\n", 1, "eval")
        self.assertRejected("x = 1\nexec('x = 2')\n", 2, "exec")
        self.assertRejected("__import__('os')\n", 1, "__import__")
        self.assertRejected("g = getattr\n", 1, "getattr")

    def test_dunder_escapes(self):
        self.assertRejected("x = ().__class__\n", 1, "__class__")
        self.assertRejected("__builtins__['eval']\n", 1, "__builtins__")

    def test_private_turtle_internals(self):
        self.assertRejected("import turtle\nt = turtle.Turtle()\nt._tracer(0)\n",
                            3, "_tracer")

    def test_routes_to_tk(self):
        self.assertRejected("import turtle\nturtle.getscreen().getcanvas()\n",
                            2, "getcanvas")
        self.assertRejected("from turtle import *\ngetcanvas()\n", 2, "getcanvas")
        self.assertRejected("from turtle import getcanvas\n", 1, "getcanvas")
        self.assertRejected("import turtle\nturtle.TK.Tk()\n", 2, "TK")

    def test_syntax_error_has_a_line(self):
        src = "import turtle\nfor i in range(3)\n    turtle.forward(10)\n"
        self.assertRejected(src, 2, "can't read")

    def test_one_problem_per_line_in_order(self):
        problems = check("import sys\nimport os\n")
        self.assertEqual(len(problems), 2)
        self.assertTrue(problems[0].startswith("Line 1: "))
        self.assertTrue(problems[1].startswith("Line 2: "))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify it fails**

Run: `python tests/test_code_check.py`
Expected: `ModuleNotFoundError: No module named 'code_check'`

- [ ] **Step 3: Implement `code_check.py`**

```python
"""
code_check.py  -  look over a student's program before it is saved or run.

    problems = check(source)      # [] means OK

Reads the code without running it and refuses anything a turtle drawing
does not need: other modules, files, eval/exec, and the back doors into
Python and Tk.  This stops accidents and casual mischief; it is not a
sandbox.  On the Pi, student programs also run as a user who can't touch
the plotter or the project files, with a time limit.
"""

import ast

ALLOWED_MODULES = ("turtle", "math", "random", "time", "colorsys")

# Built-ins that reach files, other code, or anything by name.
BANNED_NAMES = {"open", "exec", "eval", "compile", "__import__", "getattr",
                "setattr", "delattr", "globals", "locals", "vars",
                "breakpoint", "getcanvas"}

# Attributes that lead out of turtle into Tk (and from there anywhere).
BANNED_ATTRS = {"getcanvas", "cv", "tk", "TK", "sys", "os", "modules",
                "inspect", "types", "system"}

ALLOWED_DUNDERS = {"__name__"}


def _import_problem(line, name):
    return ("Line %d: plotter programs can only import %s (not %s)."
            % (line, ", ".join(ALLOWED_MODULES), name))


def _not_allowed(line, what):
    return "Line %d: %s is not allowed in plotter programs." % (line, what)


def _underscore(line, name):
    return ("Line %d: names starting with an underscore (%s) are not "
            "allowed in plotter programs." % (line, name))


def _problems(node):
    line = getattr(node, "lineno", 0)
    if isinstance(node, ast.Import):
        for alias in node.names:
            if alias.name.split(".")[0] not in ALLOWED_MODULES:
                yield _import_problem(line, alias.name)
    elif isinstance(node, ast.ImportFrom):
        module = node.module or ""
        if node.level or module.split(".")[0] not in ALLOWED_MODULES:
            yield _import_problem(line, "." * node.level + module)
        for alias in node.names:
            if alias.name in BANNED_NAMES or alias.name in BANNED_ATTRS:
                yield _not_allowed(line, alias.name)
            elif alias.name.startswith("_"):
                yield _underscore(line, alias.name)
    elif isinstance(node, ast.Name):
        if node.id in BANNED_NAMES:
            yield _not_allowed(line, node.id)
        elif node.id.startswith("__") and node.id not in ALLOWED_DUNDERS:
            yield _underscore(line, node.id)
    elif isinstance(node, ast.Attribute):
        if node.attr.startswith("_"):
            yield _underscore(line, node.attr)
        elif node.attr in BANNED_ATTRS:
            yield _not_allowed(line, "." + node.attr)


def check(source):
    """Problems with a student's program, as plain sentences.  [] = OK."""
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        return ["Line %d: Python can't read this line (%s)."
                % (e.lineno or 0, e.msg)]
    found = set()
    for node in ast.walk(tree):
        for text in _problems(node):
            found.add((getattr(node, "lineno", 0), text))
    return [text for _, text in sorted(found)]
```

- [ ] **Step 4: Run to verify it passes**

Run: `python tests/test_code_check.py`
Expected: `OK` (12 tests)

- [ ] **Step 5: Commit**

```bash
git add code_check.py tests/test_code_check.py
git commit -m "Code check: refuse student programs that are not plain turtle code

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Check and `run_as` in `run_student` (`dashboard_logic.py`)

**Files:**
- Modify: `dashboard_logic.py` (imports; `AX4_DEFAULTS`; `_PLAIN_ERRORS` line 31; `run_student` lines 48-64; add `UPLOADS`, `student_command`, `_runner_failed`)
- Test: `tests/test_dashboard_logic.py` (append classes)

**Interfaces:**
- Consumes: `code_check.check(source) -> list[str]` (Task 1).
- Produces:
  - `dashboard_logic.UPLOADS: str` — absolute path of `<project>/uploads`.
  - `dashboard_logic.student_command(path, run_as=None) -> list[str]`.
  - `dashboard_logic.run_student(path, timeout=STUDENT_TIMEOUT, run_as=None) -> dict` — same result shape as before; a refused program gives `error = {"type": "NotAllowed", "message": "<problems joined by \\n>", "line": None}` and the runner is never started.
  - `AX4_DEFAULTS` gains `"run_as": None, "stop_pin": None`.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_dashboard_logic.py`, before the `if __name__` block; add `import tempfile` and `from unittest import mock` to its imports)

```python
class TestStudentCommand(unittest.TestCase):

    def test_plain(self):
        self.assertEqual(logic.student_command("s.py"),
                         [sys.executable, logic.RUNNER, "s.py"])

    def test_run_as_uses_sudo_without_a_password_prompt(self):
        self.assertEqual(logic.student_command("s.py", "plotstudent"),
                         ["sudo", "-n", "-u", "plotstudent",
                          sys.executable, logic.RUNNER, "s.py"])

    def test_defaults_have_the_pi_keys_switched_off(self):
        self.assertIsNone(logic.AX4_DEFAULTS["run_as"])
        self.assertIsNone(logic.AX4_DEFAULTS["stop_pin"])

    def test_uploads_folder_is_in_the_project(self):
        self.assertEqual(logic.UPLOADS,
                         os.path.join(os.path.dirname(logic.RUNNER), "uploads"))


class TestRunStudentChecks(unittest.TestCase):

    def test_refused_program_is_never_run(self):
        fd, path = tempfile.mkstemp(suffix=".py")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write("import os\nos.system('echo hi')\n")
        try:
            with mock.patch.object(logic.subprocess, "run",
                                   side_effect=AssertionError("ran it")):
                r = logic.run_student(path)
        finally:
            os.remove(path)
        self.assertEqual(r["strokes"], [])
        self.assertEqual(r["error"]["type"], "NotAllowed")
        text = logic.error_text(r["error"])
        self.assertTrue(text.startswith("Line 1: "), text)
        self.assertIn("os", text)

    def test_run_as_failure_points_at_the_setup_doc(self):
        r = logic.run_student(os.path.join(SAMPLES, "square.py"), timeout=10,
                              run_as="no-such-user-ax4")
        self.assertEqual(r["error"]["type"], "RunnerFailed")
        self.assertIn("no-such-user-ax4", r["error"]["message"])
        self.assertIn("PI_SETUP", r["error"]["message"])
```

- [ ] **Step 2: Run to verify it fails**

Run: `python tests/test_dashboard_logic.py`
Expected: errors — `AttributeError: module 'dashboard_logic' has no attribute 'student_command'` (and `UPLOADS`, `KeyError: 'run_as'`).

- [ ] **Step 3: Implement**

In `dashboard_logic.py`:

Add `import code_check` after `from grbl_backend import LETTER_MM`.

After the `RUNNER = ...` line add:

```python
UPLOADS = os.path.join(os.path.dirname(RUNNER), "uploads")   # Pi upload page
```

Add two keys to `AX4_DEFAULTS` (last line of the dict):

```python
    "pen_setup_done": None, "calibrated": None,
    "run_as": None, "stop_pin": None,        # Pi only: see docs/PI_SETUP.md
```

Change `_PLAIN_ERRORS` to:

```python
_PLAIN_ERRORS = ("Timeout", "KeyboardInputNotSupported", "RunnerFailed",
                 "NotAllowed")
```

Replace `run_student` with:

```python
def student_command(path, run_as=None):
    """The command that runs a student file; as another user if run_as."""
    cmd = [sys.executable, RUNNER, path]
    if run_as:
        cmd = ["sudo", "-n", "-u", run_as] + cmd
    return cmd


def _runner_failed(detail, run_as):
    if run_as:
        return ("Couldn't run the program as user %s - see docs/PI_SETUP.md.\n%s"
                % (run_as, detail))
    return detail


def run_student(path, timeout=STUDENT_TIMEOUT, run_as=None):
    """Check a student's .py, then run it in a separate process and return
    what it drew."""
    try:
        with open(path, encoding="utf-8-sig", errors="replace") as f:
            source = f.read()
    except OSError as e:
        return _failed("RunnerFailed", str(e))
    problems = code_check.check(source)
    if problems:
        return _failed("NotAllowed", "\n".join(problems))
    flags = 0x08000000 if sys.platform == "win32" else 0   # no console window
    try:
        out = subprocess.run(student_command(path, run_as),
                             capture_output=True, text=True, encoding="utf-8",
                             errors="replace", timeout=timeout,
                             creationflags=flags)
    except subprocess.TimeoutExpired:
        return _failed("Timeout", "The program took too long - is there a "
                                  "loop that never ends?")
    except OSError as e:                     # e.g. no sudo on this machine
        return _failed("RunnerFailed", _runner_failed(str(e), run_as))
    try:
        return json.loads(out.stdout)
    except ValueError:
        last = (out.stderr.strip().splitlines() or
                ["The program could not be run."])[-1]
        return _failed("RunnerFailed", _runner_failed(last, run_as))
```

- [ ] **Step 4: Run to verify it passes**

Run: `python tests/test_dashboard_logic.py` then `python tests/test_run_turtle.py`
Expected: both `OK`.

- [ ] **Step 5: Commit**

```bash
git add dashboard_logic.py tests/test_dashboard_logic.py
git commit -m "Dashboard logic: check student code first, optional run_as user

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Self-imposed limits in `run_turtle.py`

Why: with `sudo`, the dashboard's 20 s timeout kills `sudo`, not the student's Python, so a `while True` loop would be left running. The runner therefore limits itself on Linux. No effect on Windows.

**Files:**
- Modify: `run_turtle.py` (constants near the top; new `limit_resources()`; call it first in `main`)
- Test: `tests/test_run_turtle.py` (append class)

**Interfaces:**
- Produces: `run_turtle.limit_resources()`; module constants `LIMIT_SECONDS = 25`, `LIMIT_MEMORY = 1024 * 1024 * 1024`.

- [ ] **Step 1: Write the failing test** (append to `tests/test_run_turtle.py` before `if __name__`)

```python
@unittest.skipUnless(hasattr(__import__("signal"), "alarm"), "Linux/Mac only")
class TestLimits(unittest.TestCase):

    def test_a_runaway_program_ends_itself(self):
        code = ("import sys, time; sys.path.insert(0, %r); import run_turtle; "
                "run_turtle.LIMIT_SECONDS = 1; run_turtle.limit_resources(); "
                "time.sleep(10)" % ROOT)
        start = time.time()
        out = subprocess.run([sys.executable, "-c", code], timeout=8)
        self.assertNotEqual(out.returncode, 0)
        self.assertLess(time.time() - start, 5)


class TestLimitsExist(unittest.TestCase):

    def test_limits_are_safe_to_call_here(self):
        self.assertEqual(run_turtle.LIMIT_SECONDS, 25)
        self.assertTrue(callable(run_turtle.limit_resources))
```

Add `import time` to the test file's imports.

- [ ] **Step 2: Run to verify it fails**

Run: `python tests/test_run_turtle.py`
Expected: `AttributeError: module 'run_turtle' has no attribute 'LIMIT_SECONDS'` (the Linux-only test is skipped on Windows).

- [ ] **Step 3: Implement** in `run_turtle.py`

After the `W_COLOUR = ...` line add:

```python
# On the Pi the program runs under sudo, and the dashboard's time limit
# can only kill sudo - so the runner also limits itself (Linux/Mac only).
LIMIT_SECONDS = 25                   # a bit longer than the dashboard waits
LIMIT_MEMORY = 1024 * 1024 * 1024
```

Before `def main(argv):` add:

```python
def limit_resources():
    """End this process after LIMIT_SECONDS and cap its memory.  Does
    nothing on Windows."""
    try:
        import resource
        import signal
    except ImportError:
        return
    signal.alarm(LIMIT_SECONDS)          # default action: end the process
    resource.setrlimit(resource.RLIMIT_CPU, (LIMIT_SECONDS, LIMIT_SECONDS))
    resource.setrlimit(resource.RLIMIT_AS, (LIMIT_MEMORY, LIMIT_MEMORY))
```

First line of `main(argv)` body:

```python
    limit_resources()
```

- [ ] **Step 4: Run to verify it passes**

Run: `python tests/test_run_turtle.py`
Expected: `OK (skipped=1)` on Windows.

- [ ] **Step 5: Commit**

```bash
git add run_turtle.py tests/test_run_turtle.py
git commit -m "Runner: end itself after 25 s and cap memory on Linux

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Dashboard hooks — uploads folder, run_as, STOP button, kiosk

**Files:**
- Create: `stop_button.py`
- Modify: `dashboard.py` (imports; `Dashboard.__init__`; `_poll`; `on_open`; `load_file` line 501; `main`)
- Test: `tests/test_stop_button.py` (new), `tests/test_dashboard_smoke.py` (append class)

**Interfaces:**
- Consumes: `logic.UPLOADS`, `logic.run_student(path, run_as=...)`, config keys `run_as`, `stop_pin` (Task 2).
- Produces: `stop_button.attach(pin, on_press, button_class=None) -> object or None`; `Dashboard.open_dir() -> str or None`; `Dashboard._hw_stop` (`threading.Event`); `dashboard.kiosk(root)`; `dashboard.main(argv=None)` accepting `--kiosk`.

- [ ] **Step 1: Write the failing tests**

`tests/test_stop_button.py`:

```python
"""
Tests for stop_button.py with a pretend button - no GPIO needed.

    python tests/test_stop_button.py
"""

import os
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import stop_button


class FakeButton:
    def __init__(self, pin, pull_up, bounce_time):
        self.pin = pin
        self.pull_up = pull_up
        self.when_pressed = None


class NoGpio:
    def __init__(self, *args, **kwargs):
        raise RuntimeError("no GPIO on this machine")


class TestAttach(unittest.TestCase):

    def test_no_pin_means_no_button(self):
        self.assertIsNone(stop_button.attach(None, print, FakeButton))

    def test_pressing_the_button_calls_back(self):
        presses = []
        b = stop_button.attach(17, lambda: presses.append(1), FakeButton)
        self.assertEqual(b.pin, 17)
        self.assertTrue(b.pull_up)
        b.when_pressed()
        self.assertEqual(presses, [1])

    def test_no_gpio_hardware_is_ignored(self):
        self.assertIsNone(stop_button.attach(17, print, NoGpio))

    def test_gpiozero_missing_is_ignored(self):
        with mock.patch.dict(sys.modules, {"gpiozero": None}):
            self.assertIsNone(stop_button.attach(17, print))


if __name__ == "__main__":
    unittest.main()
```

Append to `tests/test_dashboard_smoke.py` (before `if __name__`; add `import shutil`, `import tempfile`, `from unittest import mock` to its imports):

```python
class TestPiHost(unittest.TestCase):

    def test_open_starts_in_uploads_only_if_it_exists(self):
        root, d = make(FakeGrbl())
        tmp = tempfile.mkdtemp()
        try:
            with mock.patch.object(dashboard.logic, "UPLOADS", tmp):
                self.assertEqual(d.open_dir(), tmp)
            with mock.patch.object(dashboard.logic, "UPLOADS",
                                   os.path.join(tmp, "missing")):
                self.assertIsNone(d.open_dir())
        finally:
            close(root)
            shutil.rmtree(tmp)

    def test_refused_file_shows_why_and_cannot_plot(self):
        root, d = make(FakeGrbl())
        fd, path = tempfile.mkstemp(suffix=".py")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write("import os\n")
        try:
            d.load_file(path)
            self.assertIn("Line 1: ", d.info["text"])
            self.assertEqual(d.strokes, [])
            self.assertEqual(str(d.btn_plot["state"]), "disabled")
        finally:
            close(root)
            os.remove(path)

    def test_run_as_from_config_reaches_the_runner(self):
        root, d = make(FakeGrbl())
        try:
            d.config["run_as"] = "plotstudent"
            seen = {}

            def fake_run(path, run_as=None):
                seen["run_as"] = run_as
                return {"strokes": [], "warnings": [], "error": None}

            with mock.patch.object(dashboard.logic, "run_student", fake_run):
                d.load_file(os.path.join(SAMPLES, "square.py"))
            self.assertEqual(seen["run_as"], "plotstudent")
        finally:
            close(root)

    def test_hardware_stop_button_presses_stop(self):
        root, d = make(FakeGrbl())
        try:
            calls = []
            d.on_stop = lambda: calls.append(1)
            d._hw_stop.set()                 # what the GPIO thread does
            pump(root, lambda: calls, seconds=3)
            self.assertEqual(calls, [1])
            self.assertFalse(d._hw_stop.is_set())
        finally:
            close(root)
```

- [ ] **Step 2: Run to verify they fail**

Run: `python tests/test_stop_button.py` → `ModuleNotFoundError: No module named 'stop_button'`
Run: `python tests/test_dashboard_smoke.py` → the 4 new tests error (`open_dir`, `_hw_stop` missing; `fake_run` called without `run_as`).

- [ ] **Step 3: Implement**

`stop_button.py`:

```python
"""
stop_button.py  -  an optional physical STOP button on the Raspberry Pi.

Wire a push button between a GPIO pin and ground, and put the pin's BCM
number in plotter_config.json as "stop_pin".  Pressing it does exactly what
the dashboard's STOP button does.  Off when there is no stop_pin, no
gpiozero, or no GPIO (e.g. on the laptop).
"""


def attach(pin, on_press, button_class=None):
    """Call on_press (from gpiozero's own thread) when the button is
    pressed.  Returns the button, or None if there isn't one."""
    if pin is None:
        return None
    if button_class is None:
        try:
            from gpiozero import Button as button_class
        except ImportError:
            return None
    try:
        button = button_class(pin, pull_up=True, bounce_time=0.05)
    except Exception:            # gpiozero: no GPIO on this machine
        return None
    button.when_pressed = on_press
    return button
```

`dashboard.py`:

1. Imports: add `import sys` (alphabetical, after `import queue`) and `import stop_button` after `import dashboard_logic as logic`.
2. In `Dashboard.__init__`, just before `self._build()`:

```python
        self._hw_stop = threading.Event()   # set by the physical STOP button
        self._stop_button = stop_button.attach(self.config.get("stop_pin"),
                                               self._hw_stop.set)
```

3. In `_poll`, first lines inside `try:`:

```python
            if self._hw_stop.is_set():       # Tk calls only on this thread
                self._hw_stop.clear()
                self.on_stop()
```

4. Replace `on_open` with:

```python
    def open_dir(self):
        """Start the Open dialog in uploads/ (filled by the Pi's upload
        page) when it exists."""
        return logic.UPLOADS if os.path.isdir(logic.UPLOADS) else None

    def on_open(self):
        path = filedialog.askopenfilename(
            parent=self.root, title="Open a student's turtle program",
            initialdir=self.open_dir(),
            filetypes=[("Python files", "*.py"), ("All files", "*.*")])
        if path:
            self.load_file(path)
```

5. In `load_file`, change `self.result = logic.run_student(path)` to:

```python
            self.result = logic.run_student(path,
                                            run_as=self.config.get("run_as"))
```

6. Replace `main` with:

```python
def kiosk(root):
    """Fill the whole (virtual) screen - used on the Raspberry Pi."""
    root.geometry("%dx%d+0+0" % (root.winfo_screenwidth(),
                                 root.winfo_screenheight()))


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    root = tk.Tk()
    if "--kiosk" in argv:
        kiosk(root)
    Dashboard(root)
    root.mainloop()
```

- [ ] **Step 4: Run to verify they pass**

Run: `python tests/test_stop_button.py` → `OK`
Run: `python tests/test_dashboard_smoke.py` → `OK` (the pre-existing "application has been destroyed" noise is expected).
Run: `python dashboard.py --kiosk` by hand → window fills the screen; close it.

- [ ] **Step 5: Commit**

```bash
git add stop_button.py dashboard.py tests/test_stop_button.py tests/test_dashboard_smoke.py
git commit -m "Dashboard: uploads folder, run_as, GPIO STOP button, --kiosk

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Upload page (`upload_server.py`)

**Files:**
- Create: `upload_server.py`
- Modify: `.gitignore` (add `uploads/`)
- Test: `tests/test_upload_server.py`

**Interfaces:**
- Consumes: `code_check.check` (Task 1).
- Produces: `upload_server.UPLOADS`, `MAX_BYTES = 100 * 1024`, `clean_name(name) -> str`, `save_upload(folder, name, source, now=None) -> str` (file name saved), `recent(folder, n=20) -> list[str]` (newest first), `create_app(folder=UPLOADS) -> Flask`, `main(argv=None)` with `--port` (default 8000) and `--host` (default `0.0.0.0`).

- [ ] **Step 1: Write the failing tests** — `tests/test_upload_server.py`:

```python
"""
Tests for upload_server.py using Flask's test client - no network.

    python tests/test_upload_server.py
"""

import datetime
import io
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import upload_server as us

GOOD = b"import turtle\nturtle.forward(50)\n"


class TestCleanName(unittest.TestCase):

    def test_spaces_and_symbols(self):
        self.assertEqual(us.clean_name("  Ana Lee!/.. "), "Ana_Lee")

    def test_hangeul_kept(self):
        self.assertEqual(us.clean_name("김민수"), "김민수")

    def test_empty_or_only_symbols(self):
        self.assertEqual(us.clean_name(""), "student")
        self.assertEqual(us.clean_name("../"), "student")

    def test_long_names_are_cut(self):
        self.assertEqual(len(us.clean_name("a" * 50)), 30)


class TempFolder(unittest.TestCase):

    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.dir)


class TestSave(TempFolder):

    def test_same_second_does_not_overwrite(self):
        now = datetime.datetime(2026, 10, 8, 9, 30, 0)
        a = us.save_upload(self.dir, "ana", "x = 1\n", now)
        b = us.save_upload(self.dir, "ana", "x = 2\n", now)
        self.assertEqual(a, "ana_20261008-093000.py")
        self.assertEqual(b, "ana_20261008-093000_2.py")
        with open(os.path.join(self.dir, a), encoding="utf-8") as f:
            self.assertEqual(f.read(), "x = 1\n")

    def test_recent_is_newest_first(self):
        old = us.save_upload(self.dir, "old", "x = 1\n")
        new = us.save_upload(self.dir, "new", "x = 1\n")
        os.utime(os.path.join(self.dir, old), (1000, 1000))
        os.utime(os.path.join(self.dir, new), (2000, 2000))
        self.assertEqual(us.recent(self.dir), [new, old])


class TestPage(TempFolder):

    def setUp(self):
        super().setUp()
        app = us.create_app(self.dir)
        app.testing = True
        self.client = app.test_client()

    def post(self, name, filename, data):
        return self.client.post(
            "/", data={"name": name, "file": (io.BytesIO(data), filename)},
            content_type="multipart/form-data")

    def saved(self):
        return os.listdir(self.dir)

    def test_page_links_to_the_dashboard_on_the_same_host(self):
        r = self.client.get("/", base_url="http://10.0.0.5:8000")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"http://10.0.0.5:6080/vnc.html", r.data)

    def test_good_upload_is_saved(self):
        r = self.post("Ana", "spiral.py", GOOD)
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"Uploaded", r.data)
        files = self.saved()
        self.assertEqual(len(files), 1)
        self.assertTrue(files[0].startswith("Ana_"))
        self.assertIn(files[0].encode(), r.data)      # shows in the list
        with open(os.path.join(self.dir, files[0]), "rb") as f:
            self.assertEqual(f.read(), GOOD)

    def test_bad_code_is_refused_with_the_reason(self):
        r = self.post("Ana", "x.py", b"import os\n")
        self.assertEqual(self.saved(), [])
        self.assertIn(b"Line 1: ", r.data)
        self.assertIn(b"(not os)", r.data)

    def test_bom_file_is_accepted(self):
        self.post("Ana", "x.py", b"\xef\xbb\xbf" + GOOD)
        files = self.saved()
        self.assertEqual(len(files), 1)
        with open(os.path.join(self.dir, files[0]), "rb") as f:
            self.assertEqual(f.read(), GOOD)

    def test_only_py_files(self):
        r = self.post("Ana", "picture.png", GOOD)
        self.assertEqual(self.saved(), [])
        self.assertIn(b".py", r.data)

    def test_not_utf8_is_refused(self):
        r = self.post("Ana", "x.py", b"x = '\xff\xfe'\n")
        self.assertEqual(self.saved(), [])
        self.assertIn(b"UTF-8", r.data)

    def test_no_file_chosen(self):
        r = self.client.post("/", data={"name": "Ana"},
                             content_type="multipart/form-data")
        self.assertEqual(self.saved(), [])
        self.assertIn(b"Choose a file", r.data)

    def test_too_big_has_a_friendly_message(self):
        for size in (us.MAX_BYTES + 1, us.MAX_BYTES * 3):
            r = self.post("Ana", "x.py", b"#" * size)
            self.assertIn(b"too big", r.data, size)
        self.assertEqual(self.saved(), [])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify it fails**

Run: `python tests/test_upload_server.py`
Expected: `ModuleNotFoundError: No module named 'upload_server'`

- [ ] **Step 3: Implement** `upload_server.py`:

```python
"""
upload_server.py  -  the students' upload page on the Raspberry Pi.

    python3 upload_server.py            (port 8000; the Pi runs it as a service)

Students pick a .py file and type their name.  The program is checked
(code_check.py) and, if it is plain turtle code, saved in uploads/ where
the dashboard's Open dialog starts.  The page also links to the dashboard
itself (noVNC, port 6080).
"""

import argparse
import datetime
import os
import sys

from flask import Flask, render_template_string, request

import code_check

HERE = os.path.dirname(os.path.abspath(__file__))
UPLOADS = os.path.join(HERE, "uploads")
MAX_BYTES = 100 * 1024
SHOW = 20
DASHBOARD_PORT = 6080
TOO_BIG = "That file is too big for a turtle program (over 100 KB)."

PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AX4 Plotter</title>
<style>
 body { font-family: sans-serif; max-width: 40rem; margin: 1rem auto;
        padding: 0 1rem; }
 .dash { display: block; padding: 1rem; margin: 1rem 0; text-align: center;
         background: #2a6; color: white; font-size: 1.3rem;
         text-decoration: none; border-radius: 6px; }
 .ok { background: #dfd; padding: .5rem; }
 .bad { background: #fdd; padding: .5rem; }
 input, button { font-size: 1rem; margin: .3rem 0; }
</style></head><body>
<h1>AX4 Plotter</h1>
<a class="dash" href="{{ dashboard }}">Open the plotter dashboard</a>
<h2>Upload your turtle program</h2>
{% if saved %}<p class="ok">Uploaded as <b>{{ saved }}</b>.
 Open it from the dashboard with "Open student file...".</p>{% endif %}
{% if problems %}<div class="bad"><p>Not uploaded:</p><ul>
 {% for p in problems %}<li>{{ p }}</li>{% endfor %}</ul></div>{% endif %}
<form method="post" enctype="multipart/form-data">
 <label>Your name <input name="name" maxlength="30" value="{{ name }}"></label><br>
 <input type="file" name="file" accept=".py"><br>
 <button type="submit">Upload</button>
</form>
<h2>Recent uploads</h2>
<ul>{% for f in files %}<li>{{ f }}</li>{% else %}<li>None yet.</li>{% endfor %}</ul>
</body></html>"""


def clean_name(name):
    """Letters (any language), digits, - and _; spaces become _."""
    kept = "".join(c for c in name.strip().replace(" ", "_")
                   if c.isalnum() or c in "-_")
    return kept.strip("_-")[:30] or "student"


def save_upload(folder, name, source, now=None):
    """Save source as <name>_<date-time>.py, never overwriting.  Returns
    the file name."""
    now = now or datetime.datetime.now()
    base = "%s_%s" % (clean_name(name), now.strftime("%Y%m%d-%H%M%S"))
    filename, n = base + ".py", 2
    while os.path.exists(os.path.join(folder, filename)):
        filename, n = "%s_%d.py" % (base, n), n + 1
    with open(os.path.join(folder, filename), "w", encoding="utf-8",
              newline="") as f:
        f.write(source)
    return filename


def recent(folder, n=SHOW):
    """The n most recently uploaded .py files, newest first."""
    files = [f for f in os.listdir(folder) if f.endswith(".py")]
    files.sort(key=lambda f: os.path.getmtime(os.path.join(folder, f)),
               reverse=True)
    return files[:n]


def _read_upload(upload):
    """(source, problems) for an uploaded file."""
    if upload is None or not upload.filename:
        return None, ["Choose a file to upload."]
    if not upload.filename.lower().endswith(".py"):
        return None, ["Only Python files (.py) can be plotted."]
    data = upload.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        return None, [TOO_BIG]
    try:
        source = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return None, ["The file isn't saved as UTF-8 text.  Save it from "
                      "Thonny and try again."]
    return source, code_check.check(source)


def create_app(folder=UPLOADS):
    os.makedirs(folder, exist_ok=True)
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = MAX_BYTES + 16 * 1024   # form overhead

    def page(status=200, **values):
        host = request.host.split(":")[0]
        values.setdefault("name", "")
        return render_template_string(
            PAGE, files=recent(folder),
            dashboard="http://%s:%d/vnc.html?autoconnect=1&resize=scale"
                      % (host, DASHBOARD_PORT),
            **values), status

    @app.route("/", methods=["GET", "POST"])
    def index():
        if request.method == "GET":
            return page()
        name = request.form.get("name", "")
        source, problems = _read_upload(request.files.get("file"))
        if problems:
            return page(problems=problems, name=name)
        return page(saved=save_upload(folder, name, source), name=name)

    @app.errorhandler(413)
    def too_big(e):
        return page(413, problems=[TOO_BIG])

    return app


def main(argv=None):
    parser = argparse.ArgumentParser(description="AX4 plotter upload page")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--host", default="0.0.0.0")
    args = parser.parse_args(argv)
    create_app().run(host=args.host, port=args.port, threaded=True)


if __name__ == "__main__":
    sys.exit(main())
```

Note for `test_good_upload_is_saved`: `GOOD` contains `\n` only and the file is written with `newline=""`, so bytes match exactly.

Add to `.gitignore` (after the `.superpowers/` line):

```
# student uploads on the Pi
uploads/
```

- [ ] **Step 4: Run to verify it passes**

Run: `python tests/test_upload_server.py`
Expected: `OK` (14 tests). Then by hand: `python upload_server.py`, open `http://localhost:8000/`, upload `tests/samples/square.py` and a file containing `import os`; check both messages; Ctrl-C; delete the `uploads/` folder it made.

- [ ] **Step 5: Commit**

```bash
git add upload_server.py tests/test_upload_server.py .gitignore
git commit -m "Upload page: students upload checked turtle programs to uploads/

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Pi setup files (`pi/`)

**Files:**
- Create: `pi/setup.sh`, `pi/start-display.sh`, `pi/plotter-display.service`, `pi/plotter-vnc.service`, `pi/plotter-novnc.service`, `pi/plotter-upload.service`, `.gitattributes`
- Test: `tests/test_pi_files.py`

**Interfaces:**
- Consumes: `dashboard.py --kiosk` (Task 4), `upload_server.py` (Task 5), config key `run_as` (Task 2).
- Produces: installed app at `/opt/ax4plotter`; services `plotter-display`, `plotter-vnc`, `plotter-novnc`, `plotter-upload`; user `plotstudent`; sudoers file `/etc/sudoers.d/ax4plotter`.

- [ ] **Step 1: Write the failing test** — `tests/test_pi_files.py`:

```python
"""
Checks on the Raspberry Pi setup files that can be made on Windows:
line endings (bash and systemd choke on CR), shebangs, bash syntax, and
that every service file is filled in by setup.sh.

    python tests/test_pi_files.py
"""

import glob
import os
import shutil
import subprocess
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PI = os.path.join(ROOT, "pi")
SCRIPTS = ("setup.sh", "start-display.sh")
SERVICES = ("plotter-display.service", "plotter-vnc.service",
            "plotter-novnc.service", "plotter-upload.service")


def read(name):
    with open(os.path.join(PI, name), "rb") as f:
        return f.read()


class TestPiFiles(unittest.TestCase):

    def test_all_files_exist(self):
        for name in SCRIPTS + SERVICES:
            self.assertTrue(os.path.isfile(os.path.join(PI, name)), name)

    def test_no_windows_line_endings(self):
        for path in glob.glob(os.path.join(PI, "*")):
            with open(path, "rb") as f:
                self.assertNotIn(b"\r", f.read(), path)

    def test_scripts_are_bash(self):
        for name in SCRIPTS:
            self.assertTrue(read(name).startswith(b"#!/bin/bash\n"), name)

    @unittest.skipUnless(shutil.which("bash"), "no bash here")
    def test_scripts_parse(self):
        for name in SCRIPTS:
            out = subprocess.run(["bash", "-n", os.path.join(PI, name)],
                                 capture_output=True, text=True)
            self.assertEqual(out.returncode, 0, name + ": " + out.stderr)

    def test_services_use_the_placeholders_setup_fills(self):
        for name in SERVICES:
            text = read(name).decode()
            self.assertIn("User=@USER@", text, name)
            self.assertIn("[Install]", text, name)
            self.assertIn("Restart=always", text, name)

    def test_setup_installs_every_service(self):
        text = read("setup.sh").decode()
        for name in SERVICES:
            self.assertIn(name.replace(".service", ""), text, name)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify it fails**

Run: `python tests/test_pi_files.py`
Expected: FAIL — files do not exist.

- [ ] **Step 3: Create the files**

`.gitattributes`:

```
# Files run on the Raspberry Pi must keep LF endings.
pi/* text eol=lf
*.sh text eol=lf
```

`pi/start-display.sh`:

```bash
#!/bin/bash
# Start the virtual screen :1, a window manager, then the dashboard on it.
# Run by plotter-display.service.  When the dashboard closes, this script
# ends and systemd starts it all again.
set -e
export DISPLAY=:1
rm -f /tmp/.X1-lock /tmp/.X11-unix/X1        # left over from a crash
Xvfb :1 -screen 0 1280x800x24 -nolisten tcp &
for i in $(seq 50); do
    xdpyinfo >/dev/null 2>&1 && break
    sleep 0.1
done
openbox &
xhost +SI:localuser:plotstudent >/dev/null   # student programs draw here
cd "$(dirname "$0")/.."
exec python3 dashboard.py --kiosk
```

`pi/plotter-display.service`:

```
[Unit]
Description=AX4 plotter dashboard on virtual screen :1
After=network.target

[Service]
User=@USER@
WorkingDirectory=@APP@
ExecStart=@APP@/pi/start-display.sh
Restart=always
RestartSec=2

[Install]
WantedBy=multi-user.target
```

`pi/plotter-vnc.service`:

```
[Unit]
Description=Share screen :1 over VNC (local only; noVNC serves it)
After=plotter-display.service

[Service]
User=@USER@
ExecStart=/usr/bin/x11vnc -display :1 -shared -forever -nopw -localhost -rfbport 5900 -quiet
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

`pi/plotter-novnc.service`:

```
[Unit]
Description=Show the plotter dashboard in a browser on port 6080
After=plotter-vnc.service

[Service]
User=@USER@
ExecStart=/usr/bin/websockify --web /usr/share/novnc 6080 localhost:5900
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

`pi/plotter-upload.service`:

```
[Unit]
Description=AX4 plotter upload page on port 8000
After=network.target

[Service]
User=@USER@
WorkingDirectory=@APP@
ExecStart=/usr/bin/python3 @APP@/upload_server.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

`pi/setup.sh`:

```bash
#!/bin/bash
# One-time (and update) setup of the AX4 plotter on a Raspberry Pi.
# Copy the project folder to the Pi, then from inside it run:
#     sudo ./pi/setup.sh
# Safe to run again after copying a newer version: it keeps the Pi's
# plotter_config.json and the uploads.
set -euo pipefail

if [ "$(id -u)" != 0 ]; then
    echo "Run it with sudo:  sudo ./pi/setup.sh"
    exit 1
fi
USER_NAME="${SUDO_USER:-}"
if [ -z "$USER_NAME" ] || [ "$USER_NAME" = root ]; then
    echo "Run it with sudo from your normal account, not as root."
    exit 1
fi
SRC="$(cd "$(dirname "$0")/.." && pwd)"
APP=/opt/ax4plotter
SERVICES="plotter-display plotter-vnc plotter-novnc plotter-upload"

echo "== Installing packages"
apt-get update
apt-get install -y xvfb openbox x11vnc novnc websockify x11-utils \
    x11-xserver-utils python3-tk python3-serial python3-flask \
    python3-gpiozero rsync

echo "== Turning off OctoPrint (it would hold the plotter's USB port)"
systemctl disable --now octoprint 2>/dev/null || true

echo "== Users"
id plotstudent >/dev/null 2>&1 || \
    useradd --system --no-create-home --shell /usr/sbin/nologin plotstudent
usermod -aG dialout "$USER_NAME"

echo "== Copying the program to $APP"
mkdir -p "$APP"
EXCLUDES=(--exclude .git --exclude uploads --exclude __pycache__
          --exclude .superpowers)
if [ -f "$APP/plotter_config.json" ]; then
    EXCLUDES+=(--exclude plotter_config.json)    # keep the Pi's settings
fi
rsync -a --delete "${EXCLUDES[@]}" "$SRC/" "$APP/"
mkdir -p "$APP/uploads"
python3 - "$APP/plotter_config.json" <<'EOF'
import json, sys
path = sys.argv[1]
try:
    with open(path, encoding="utf-8") as f:
        cfg = json.load(f)
except (OSError, ValueError):
    cfg = {}
cfg["run_as"] = "plotstudent"
with open(path, "w", encoding="utf-8") as f:
    json.dump(cfg, f, indent=2, sort_keys=True)
EOF
chown -R "$USER_NAME:$USER_NAME" "$APP"
chmod -R a+rX,go-w "$APP"
chmod 755 "$APP"/pi/*.sh

echo "== Letting the dashboard run student programs as plotstudent"
cat > /etc/sudoers.d/ax4plotter <<EOF
Defaults:$USER_NAME env_keep += "DISPLAY"
$USER_NAME ALL=(plotstudent) NOPASSWD: /usr/bin/python3
EOF
chmod 440 /etc/sudoers.d/ax4plotter
visudo -cf /etc/sudoers.d/ax4plotter

echo "== Services"
for s in $SERVICES; do
    sed "s#@USER@#$USER_NAME#g; s#@APP@#$APP#g" "$APP/pi/$s.service" \
        > "/etc/systemd/system/$s.service"
done
systemctl daemon-reload
systemctl enable $SERVICES
systemctl restart $SERVICES

IP="$(hostname -I | awk '{print $1}')"
echo
echo "Done."
echo "  Dashboard:    http://$IP:6080/vnc.html?autoconnect=1&resize=scale"
echo "  Upload page:  http://$IP:8000/"
```

- [ ] **Step 4: Run to verify it passes**

Run: `python tests/test_pi_files.py`
Expected: `OK`. If `test_no_windows_line_endings` fails, the editor wrote CRLF: run `git add --renormalize pi .gitattributes` after committing `.gitattributes`, or convert with `sed -i 's/\r$//' pi/*`.

- [ ] **Step 5: Commit**

```bash
git add .gitattributes pi tests/test_pi_files.py
git commit -m "Pi: setup script and services for dashboard, noVNC and uploads

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: `docs/PI_SETUP.md` and full test run

**Files:**
- Create: `docs/PI_SETUP.md`
- Modify: `SESSION_NOTES.md` (append status)

- [ ] **Step 1: Write `docs/PI_SETUP.md`**

````markdown
# Running the AX4 plotter from a Raspberry Pi

The Pi sits next to the AX4 and does all the plotting.  Anyone on the school
network can watch and drive the dashboard from a browser, and students upload
their programs from a web page.  Plots keep going when every browser closes.

| What | Address |
|---|---|
| Dashboard | `http://<pi-ip>:6080/vnc.html?autoconnect=1&resize=scale` |
| Upload page (links to the dashboard) | `http://<pi-ip>:8000/` |

## What you need

- A Raspberry Pi 3B+ or newer running Raspberry Pi OS (Bookworm, Lite is fine).
  An old OctoPi card works if `cat /etc/os-release` says bookworm; if it says
  bullseye or older, re-flash with Raspberry Pi OS Lite (64-bit) using
  Raspberry Pi Imager, and turn on SSH in the Imager settings.
- The official Pi power supply.  A weak supply causes random USB drop-outs
  mid-plot.
- SSH access from the laptop (`ssh <user>@<pi-ip>`).

## First-time setup

1. Copy the project folder to the Pi.  From Git Bash on the laptop:

       scp -r ~/claude_code/thonny_plotter <user>@<pi-ip>:~/ax4plotter

2. On the Pi:

       cd ~/ax4plotter
       sudo ./pi/setup.sh

   It installs what it needs, turns OctoPrint off, copies the program to
   `/opt/ax4plotter`, and starts four services.  It prints the two addresses
   at the end.

3. Open the dashboard address in a browser.  You should see the dashboard.
4. Plug in the AX4 and go through the usual checklist: Connect, pen setup,
   origin.

To update later: copy the folder again and re-run `sudo ./pi/setup.sh`.
The Pi's own `plotter_config.json` (pen and calibration settings) and the
uploads are kept.

## Things to know

- **Closing the dashboard window restarts it, and that resets the AX4.**
  The AX4 forgets its origin whenever its USB port is opened.  After a
  restart, set the origin again (the checklist won't let you plot until
  you do).  Don't close the dashboard window during a lesson.
- **Everyone shares one screen and one mouse.**  Agree who is driving.
- **Uploads** are checked before they are saved: only `turtle`, `math`,
  `random`, `time` and `colorsys` can be imported, and files, `eval`,
  `exec` and similar are refused.  Student programs run as the user
  `plotstudent`, who can't use the plotter or change any files, and are
  stopped after 20-25 seconds.
- Uploads collect in `/opt/ax4plotter/uploads/`.  Delete old ones by hand
  when the list gets long.
- The Open dialog is the plain Linux one.  It starts in the uploads folder.

## Physical STOP button (optional)

Wire a push button between **GPIO 17** (pin 11) and **ground** (pin 9).
Add this to `/opt/ax4plotter/plotter_config.json`:

    "stop_pin": 17,

then `sudo systemctl restart plotter-display` (and set the origin again).
Pressing it does exactly what the red STOP button does.  The AX4 power
switch is still the last resort.

## When something is wrong

| Problem | Try |
|---|---|
| Dashboard page won't load | `sudo systemctl status plotter-display plotter-vnc plotter-novnc` |
| Black screen in the browser | `sudo systemctl restart plotter-display plotter-vnc` |
| Upload page won't load | `sudo systemctl status plotter-upload` |
| "Couldn't run the program as user plotstudent" | Re-run `sudo ./pi/setup.sh` |
| Connect says the plotter isn't found | Check the USB cable; `ls /dev/ttyUSB*` should list a port |
| Connect says the port is in use | `sudo systemctl disable --now octoprint` |
| See recent errors | `journalctl -u plotter-display -n 50` |
````

- [ ] **Step 2: Run every test file**

Run (Git Bash): `for f in tests/test_*.py; do python "$f" 2>&1 | tail -1; done`
Expected: every line `OK` (some with `skipped=`).

- [ ] **Step 3: Update `SESSION_NOTES.md`** — replace the "Next: implementation plan." sentence of the "Pi web host - DESIGN" section with a short status: code complete and tested on Windows; Pi bring-up at home (Task 8) and AX4 acceptance at school still to do.

- [ ] **Step 4: Commit**

```bash
git add docs/PI_SETUP.md SESSION_NOTES.md
git commit -m "Docs: Raspberry Pi setup guide

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: Bring-up on the Pi at home (manual, with the teacher; no AX4)

Hands-on.  The teacher runs the commands, or gives SSH access and approves each step.  Nothing here touches the plotter.

- [ ] **Step 1:** `ssh <user>@<pi-ip> cat /etc/os-release` — confirm Bookworm (else re-flash per PI_SETUP.md).
- [ ] **Step 2:** Copy and run setup exactly as in PI_SETUP.md "First-time setup" steps 1-2. Expected: ends with "Done." and two addresses.
- [ ] **Step 3:** `systemctl is-active plotter-display plotter-vnc plotter-novnc plotter-upload` → four `active`.
- [ ] **Step 4:** Open the dashboard address from the laptop **and** a phone at the same time. Both show the dashboard; a click on one shows on the other.
- [ ] **Step 5:** Upload `tests/samples/square.py` from the phone at `:8000`. In the dashboard, "Open student file..." starts in `uploads/` and shows it; opening it previews a square.
- [ ] **Step 6:** Upload a file containing `import os` → refused with "Line 1: ...". Place one directly into `/opt/ax4plotter/uploads/` with `scp` and open it in the dashboard → refused in the info area.
- [ ] **Step 7:** Upload `tests/samples/forever.py` and open it → "took too long" after 20 s; then `ps aux | grep run_turtle` shows nothing left running after 30 s.
- [ ] **Step 8:** Click Connect with no plotter plugged in → the friendly "not found" message.
- [ ] **Step 9:** `sudo reboot`; after ~1 minute both addresses work again with no login.
- [ ] **Step 10 (if a button is wired):** set `stop_pin`, restart `plotter-display`, press it → status changes as for STOP (with nothing connected it does nothing; confirm no error in `journalctl -u plotter-display -n 20`).
- [ ] **Step 11:** Record results (and any fixes) in `SESSION_NOTES.md` and `docs/HARDWARE_NOTES.md`; commit.

**At school (later, separate session):** plug in the AX4, Connect, pen setup, origin, plot `square.py`, STOP mid-plot, start another plot and close every browser — it must finish.
