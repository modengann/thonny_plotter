"""
dashboard_wizards.py  -  step-by-step Pen setup and Calibrate distances.

Written for someone doing this for the first time, maybe years from now.
Each step is one screen with plain instructions and one or two buttons.
"""

import tkinter as tk
from tkinter import messagebox, ttk

import dashboard_logic as logic
from plotter import PlotterError


class Wizard(tk.Toplevel):
    """A small window that shows one step at a time."""

    def __init__(self, dash, title):
        super().__init__(dash.root)
        self.dash = dash
        self.b = dash.backend
        self.title(title)
        self.transient(dash.root)
        self.text = ttk.Label(self, wraplength=440, justify="left", padding=12)
        self.text.pack(fill="x")
        self.extra = ttk.Frame(self, padding=(12, 0))
        self.extra.pack(fill="x")
        self.buttons = ttk.Frame(self, padding=12)
        self.buttons.pack(fill="x")

    def step(self, text, buttons):
        """Show `text` and a row of (label, callback) buttons."""
        self.text.config(text=text)
        for w in self.extra.winfo_children() + self.buttons.winfo_children():
            w.destroy()
        for label, callback in buttons:
            ttk.Button(self.buttons, text=label,
                       command=callback).pack(side="left", padx=4)

    def act(self, fn, *args):
        """Run a plotter action; on a problem show it and return False."""
        try:
            fn(*args)
            return True
        except PlotterError as e:
            messagebox.showerror("Plotter", str(e), parent=self)
            self.dash._sync_from_backend()
            self.dash.refresh()
            return False


class PenSetupWizard(Wizard):

    def __init__(self, dash):
        super().__init__(dash, "Pen setup")
        self.s1()

    def s1(self):
        if not self.act(self.b.servo, None):
            return
        self.step("Step 1 of 4\n\n"
                  "The pen holder is now lifted.\n"
                  "Loosen the pen clamp and take the pen out.",
                  [("Next", self.s2), ("Pen is already set - skip to test",
                                       self.s4)])

    def s2(self):
        self.step("Step 2 of 4\n\n"
                  "Put a sheet of paper under the pen holder.\n"
                  "Then click 'Lower to touch position'.",
                  [("Lower to touch position", self.s3)])

    def s3(self):
        if not self.act(self.b.servo, self.b.pen_touch_s):
            return
        self.step("Step 3 of 4\n\n"
                  "Slide the pen down into the clamp until the tip just "
                  "touches the paper, then tighten the clamp.\n\n"
                  "The pen should rest on the paper - not on the bottom of "
                  "its holder.  It needs a little room to move down so it "
                  "can follow bumps in the paper.",
                  [("Next", self.s4)])
        self._advanced()

    def s4(self):
        if not self.act(self.b.servo, None):
            return
        if not self.b.origin_set:
            self.step("Step 4 of 4 - test\n\n"
                      "The test draws in the middle of the sheet, so the "
                      "plotter needs to know where the sheet is.\n\n"
                      "Close this window.  Use the arrow buttons to move the "
                      "pen to the origin corner of the sheet and click "
                      "'Set origin here'.  Then open Pen setup again and "
                      "choose 'skip to test'.",
                      [("Close", self.destroy)])
            return
        self.step("Step 4 of 4 - test\n\n"
                  "The plotter will draw three small zigzags in the middle "
                  "of the sheet.",
                  [("Draw test", self.s4_draw)])

    def s4_draw(self):
        self.step("Drawing the test...", [])
        self.dash.start_job(logic.zigzag_strokes(self.dash.area), "Pen test",
                            on_done=self.s5)

    def s5(self):
        if not self.winfo_exists():      # wizard closed while drawing
            return
        self.step("What do you see on the paper?",
                  [("Solid lines", self.done),
                   ("Faint, gaps or nothing", self.too_high),
                   ("Lines joining the zigzags", self.not_lifting)])

    def too_high(self):
        self.step("The pen isn't pressing on the paper.\n\n"
                  "Click 'Lower to touch position', loosen the clamp, slide "
                  "the pen about 1 mm further down, tighten, then test "
                  "again.",
                  [("Lower to touch position", self.s3)])

    def not_lifting(self):
        self.step("The pen isn't lifting between lines.\n\n"
                  "Check that the servo arm (the small white horn) pushes "
                  "the pen holder up when the pen is up.  If the horn has "
                  "slipped, take out its screw, refit it so it lifts the "
                  "holder, and run Pen setup again.",
                  [("Close", self.destroy)])

    def done(self):
        self.dash.mark_pen_setup()
        self.step("Pen setup is done.", [("Close", self.destroy)])

    def _advanced(self):
        box = ttk.LabelFrame(self.extra, text="Advanced - only if a different "
                             "pen or servo needs other numbers")
        box.pack(fill="x", pady=6)
        for label, attr in (("Touch position (S)", "pen_touch_s"),
                            ("Pen down (S)", "pen_down_s")):
            row = ttk.Frame(box)
            row.pack(fill="x")
            ttk.Label(row, text=label, width=18).pack(side="left")
            var = tk.IntVar(value=getattr(self.b, attr))
            scale = tk.Scale(row, from_=0, to=150, orient="horizontal",
                             variable=var, length=240)
            scale.pack(side="left")

            def changed(_event, var=var, attr=attr):
                value = int(var.get())
                setattr(self.b, attr, value)
                self.act(self.b.servo, value)
                self.dash.save_setting(**{attr: value})
            scale.bind("<ButtonRelease-1>", changed)


class CalibrationWizard(Wizard):

    def __init__(self, dash):
        super().__init__(dash, "Calibrate distances")
        self.new = None
        if not (dash.check.pen_setup_done and self.b.origin_set):
            self.step("Before calibrating: run Pen setup, put down a fresh "
                      "sheet, move the pen to its origin corner and click "
                      "'Set origin here'.",
                      [("Close", self.destroy)])
            return
        self.s1()

    def s1(self):
        self.step("Step 1 of 3\n\n"
                  "The plotter will draw an L: a 150 mm line across and a "
                  "150 mm line up, with a short tick at the far end of each.",
                  [("Draw the L", self.draw)])

    def draw(self):
        self.step("Drawing...", [])
        self.dash.start_job(logic.calibration_strokes(self.dash.area),
                            "Calibration L",
                            on_done=self.s2)

    def s2(self):
        if not self.winfo_exists():      # wizard closed while drawing
            return
        self.step("Step 2 of 3\n\n"
                  "With a ruler, measure each line from the corner of the L "
                  "to the middle of its tick.  Type the lengths in "
                  "millimetres.",
                  [("Calculate", self.calc)])
        self.vx, self.vy = tk.StringVar(), tk.StringVar()
        for label, var in (("Line across (X), mm", self.vx),
                           ("Line up (Y), mm", self.vy)):
            row = ttk.Frame(self.extra)
            row.pack(fill="x", pady=2)
            ttk.Label(row, text=label, width=22).pack(side="left")
            ttk.Entry(row, textvariable=var, width=8).pack(side="left")

    def calc(self):
        try:
            mx, my = float(self.vx.get()), float(self.vy.get())
        except ValueError:
            messagebox.showerror("Calibrate", "Please type two numbers, "
                                 "like 149.5", parent=self)
            return
        settings = {}
        if not self.act(lambda: settings.update(self.b.read_settings())):
            return
        current = settings.get(100, 80.0)
        try:
            self.new, differ = logic.calibration_result(current, mx, my)
        except ValueError as e:
            messagebox.showerror("Calibrate", str(e), parent=self)
            return
        note = ("\n\nX and Y came out more than 1% different.  This plotter "
                "moves both directions with the same two motors, so one "
                "number is used for both (the average)." if differ else "")
        self.step("Step 3 of 3\n\n"
                  "Steps per mm: %.3f  ->  %.3f%s\n\n"
                  "Click Apply to store this in the plotter."
                  % (current, self.new, note),
                  [("Apply", self.apply), ("Cancel", self.destroy)])

    def apply(self):
        if not self.act(self.b.write_setting, 100, self.new):
            return
        if not self.act(self.b.write_setting, 101, self.new):
            return
        # The plotter's sense of distance just changed: the old origin
        # no longer means the same place.
        self.b.origin_set = False
        self.dash.check.origin_set = False
        self.dash.mark_calibrated()
        self.step("Saved.\n\n"
                  "Set the origin again before the next plot.  To check, "
                  "put down a fresh sheet, set the origin, and run "
                  "Calibrate distances again: both lines should now "
                  "measure 150 mm.",
                  [("Close", self.destroy)])
