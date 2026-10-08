"""
dashboard.py  -  the teacher's control window for the AX4 pen plotter.

    python dashboard.py        (or open it in Thonny and press Run)

Open a student's emailed turtle program, check the preview, and plot it.
First-time setup: docs/SETUP.md.
"""

import datetime
import os
import queue
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import dashboard_logic as logic
import stop_button
from grbl_backend import GrblBackend, LETTER_MM, PlotStopped, usable_half
from plotter import PlotterError, load_config, save_config

PX_PER_MM = 2.0
JOG_STEPS = (1, 10)


class Tooltip:
    """Show text(), worked out on hover, beside a widget.  Nothing when it
    returns None."""

    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tip = None
        widget.bind("<Enter>", self.show, add="+")
        widget.bind("<Leave>", self.hide, add="+")

    def show(self, event=None):
        text = self.text()
        if not text or self.tip:
            return
        x = self.widget.winfo_rootx() + 10
        y = self.widget.winfo_rooty() - 30
        self.tip = tk.Toplevel(self.widget)
        self.tip.wm_overrideredirect(True)
        self.tip.wm_geometry("+%d+%d" % (x, y))
        tk.Label(self.tip, text=text, bg="#ffffe0", relief="solid",
                 borderwidth=1, padx=4, pady=2).pack()

    def hide(self, event=None):
        if self.tip:
            self.tip.destroy()
            self.tip = None


class Dashboard:

    def __init__(self, root, backend=None):
        self.root = root
        root.title("AX4 Plotter")
        self.raw_config = load_config()
        self.config = logic.ax4_config(self.raw_config)
        self.half = usable_half(margin=float(self.config["margin_mm"]))
        self.backend = backend or GrblBackend(self.config)
        self.port = None             # None = find the CH340 automatically
        self.check = logic.Checklist(self.config)
        self.strokes = []            # turtle units from the student file
        self.result = None
        self.path = None
        self.plotting = False
        self.paused = False
        self._on_done = None
        self._worker = None          # the plot thread, while one runs
        self._job = None             # timing of the plot in progress
        self.jogging = False         # a hold-to-move jog is running
        self._jog_held = False       # an arrow button is pressed right now
        self._jog_timer = None       # pending "start holding" callback
        self.events = queue.Queue()
        self._hw_stop = threading.Event()   # set by the physical STOP button
        self._stop_button = stop_button.attach(self.config.get("stop_pin"),
                                               self._hw_stop.set)
        self._build()
        self.refresh()
        self._show_position()
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        root.after(100, self._poll)

    # ---- layout ---------------------------------------------------------

    def _build(self):
        r = self.root
        top = ttk.Frame(r, padding=6)
        top.grid(row=0, column=0, columnspan=3, sticky="ew")
        self.check_labels = {}
        for i, key in enumerate(("connected", "pen", "origin", "calibrated")):
            lab = ttk.Label(top, width=30)
            lab.grid(row=0, column=i, padx=4, sticky="w")
            self.check_labels[key] = lab
        self.banner = tk.Label(top, bg="#ffe066", fg="black", anchor="w")
        self.banner.grid(row=1, column=0, columnspan=4, sticky="ew", pady=(4, 0))
        self.status = ttk.Label(top, anchor="w")
        self.status.grid(row=2, column=0, columnspan=4, sticky="ew", pady=(4, 0))

        left = ttk.Frame(r, padding=6)
        left.grid(row=1, column=0, sticky="ns")
        self.btn_connect = ttk.Button(left, text="Connect", command=self.on_connect)
        self.btn_connect.pack(fill="x")
        ttk.Label(left, text="Move head (pen up)").pack(pady=(12, 0))
        self.jog_step = tk.IntVar(value=10)
        steps = ttk.Frame(left)
        steps.pack()
        for s in JOG_STEPS:
            ttk.Radiobutton(steps, text="%d mm" % s, value=s,
                            variable=self.jog_step).pack(side="left")
        pad = ttk.Frame(left)
        pad.pack()
        self.jog_buttons = []
        for text, dx, dy, row, col in (("Up", 0, 1, 0, 1), ("Left", -1, 0, 1, 0),
                                       ("Right", 1, 0, 1, 2), ("Down", 0, -1, 2, 1)):
            # click = one step; hold = keep moving until let go
            b = ttk.Button(pad, text=text, width=6)
            b.bind("<ButtonPress-1>",
                   lambda e, dx=dx, dy=dy: self.on_jog_press(dx, dy))
            b.bind("<ButtonRelease-1>", lambda e: self.on_jog_release())
            b.grid(row=row, column=col)
            self.jog_buttons.append(b)
        # where the head is, so the sheet's edges can be found and noted
        self.pos_label = ttk.Label(left, justify="center",
                                   font=("Courier", 10, "bold"))
        self.pos_label.pack(pady=(6, 0))
        ttk.Label(left, text="Go to (pen up)").pack(pady=(10, 0))
        goto = ttk.Frame(left)
        goto.pack()
        self.goto_buttons = []
        # corners of the dashed drawable area; +Y is the top of the sheet
        for text, fx, fy, row, col in (("Top L", -1, 1, 0, 0),
                                       ("Top R", 1, 1, 0, 2),
                                       ("Origin", 0, 0, 1, 1),
                                       ("Bot L", -1, -1, 2, 0),
                                       ("Bot R", 1, -1, 2, 2)):
            b = ttk.Button(goto, text=text, width=6,
                           command=lambda fx=fx, fy=fy: self.on_goto(fx, fy))
            b.grid(row=row, column=col)
            self.goto_buttons.append(b)
        self.btn_origin = ttk.Button(left, text="Set origin here",
                                     command=self.on_set_origin)
        self.btn_pen_up = ttk.Button(left, text="Pen up",
                                     command=lambda: self.on_pen(False))
        self.btn_pen_down = ttk.Button(left, text="Pen down",
                                       command=lambda: self.on_pen(True))
        self.btn_change = ttk.Button(left, text="Change pen",
                                     command=self.on_change_pen)
        self.btn_pen_setup = ttk.Button(left, text="Pen setup...",
                                        command=self.on_pen_setup)
        self.btn_calibrate = ttk.Button(left, text="Calibrate distances...",
                                        command=self.on_calibrate)
        for b in (self.btn_origin, self.btn_pen_up, self.btn_pen_down,
                  self.btn_change, self.btn_pen_setup, self.btn_calibrate):
            b.pack(fill="x", pady=(8, 0))

        w = int(LETTER_MM[0] * PX_PER_MM) + 20
        h = int(LETTER_MM[1] * PX_PER_MM) + 20
        self.canvas = tk.Canvas(r, width=w, height=h, bg="#ddd",
                                highlightthickness=0)
        self.canvas.grid(row=1, column=1, padx=6, pady=6)

        right = ttk.Frame(r, padding=6)
        right.grid(row=1, column=2, sticky="ns")
        self.file_label = ttk.Label(right, text="No student file open",
                                    font=("TkDefaultFont", 10, "bold"))
        self.file_label.pack(anchor="w")
        self.info = ttk.Label(right, justify="left", wraplength=340)
        self.info.pack(anchor="w", pady=4)
        self.code = tk.Text(right, width=50, height=24, font=("Courier", 9),
                            state="disabled")
        self.code.pack(fill="both", expand=True)

        bottom = ttk.Frame(r, padding=6)
        bottom.grid(row=2, column=0, columnspan=3, sticky="ew")
        ttk.Button(bottom, text="Open student file...",
                   command=self.on_open).pack(side="left")
        ttk.Label(bottom, text="   or text:").pack(side="left")
        self.text = tk.StringVar()
        entry = ttk.Entry(bottom, textvariable=self.text, width=22)
        entry.pack(side="left")
        entry.bind("<Return>", lambda e: self.on_use_text())
        ttk.Button(bottom, text="Use text",
                   command=self.on_use_text).pack(side="left", padx=2)
        ttk.Label(bottom, text="   Scale %").pack(side="left")
        self.scale = tk.IntVar(value=100)
        sb = ttk.Spinbox(bottom, from_=1, to=logic.MAX_SCALE, width=5,
                         textvariable=self.scale, command=self.refresh)
        sb.pack(side="left")
        sb.bind("<Return>", lambda e: self.refresh())
        sb.bind("<FocusOut>", lambda e: self.refresh())
        Tooltip(sb, self.size_tip)
        ttk.Button(bottom, text="Fit to paper",
                   command=self.on_fit).pack(side="left", padx=2)
        ttk.Button(bottom, text="Reset 100%",
                   command=self.on_reset_scale).pack(side="left")
        self.btn_plot = ttk.Button(bottom, text="Plot", command=self.on_plot)
        self.btn_pause = ttk.Button(bottom, text="Pause", command=self.on_pause)
        self.btn_stop = tk.Button(bottom, text="STOP", bg="#d33", fg="white",
                                  font=("TkDefaultFont", 10, "bold"),
                                  command=self.on_stop)
        self.btn_svg = ttk.Button(bottom, text="Save SVG...",
                                  command=self.on_save_svg)
        for b in (self.btn_plot, self.btn_pause, self.btn_stop, self.btn_svg):
            b.pack(side="left", padx=4)
        self.progress = ttk.Progressbar(bottom, length=220)
        self.progress.pack(side="left", padx=8)

    # ---- state ----------------------------------------------------------

    def _scale(self):
        try:
            v = int(self.scale.get())
        except (tk.TclError, ValueError):
            v = 100
        return max(1, min(logic.MAX_SCALE, v))

    def strokes_mm(self):
        return logic.to_mm(self.strokes, self._scale())

    def size_tip(self):
        """Hover text for the Scale box: the drawing's size at this scale."""
        mm = self.strokes_mm()
        if not mm:
            return None
        w, h = logic.size_mm(mm)
        return "Estimated size: %.0f x %.0f mm at %d%%" % (w, h, self._scale())

    def _sync_from_backend(self):
        self.check.connected = self.backend.connected
        self.check.origin_set = self.backend.origin_set
        self._read_position()

    def _read_position(self):
        """Ask the plotter where the head is, unless a plot or jog thread
        is using the port (then it keeps backend.work_pos fresh itself)."""
        worker = self._worker
        if (self.backend.connected and not self.plotting and not self.jogging
                and (worker is None or not worker.is_alive())):
            try:
                self.backend.work_position()
            except PlotterError:
                pass
        self._show_position()

    def _show_position(self):
        pos = self.backend.work_pos if self.backend.connected else None
        if pos is None:
            self.pos_label.config(text="X   ---   Y   ---")
            return
        where = ("from origin" if self.backend.origin_set
                 else "from start (no origin)")
        if not self.check.calibrated:
            where += "\nnot calibrated"
        self.pos_label.config(text="X %7.1f  Y %7.1f\nmm %s"
                              % (pos[0], pos[1], where))

    def refresh(self):
        c = self.check
        tick = lambda ok: "[x] " if ok else "[ ] "
        self.check_labels["connected"].config(text=tick(c.connected) + "Connected to AX4")
        self.check_labels["pen"].config(text=tick(c.pen_setup_done) + "Pen set up")
        self.check_labels["origin"].config(text=tick(c.origin_set) + "Origin set")
        self.check_labels["calibrated"].config(
            text=tick(c.calibrated) + ("Calibrated %s" % c.calibrated
                                       if c.calibrated else "Distances calibrated"))
        if c.banner:
            self.banner.config(text=c.banner)
            self.banner.grid()
        else:
            self.banner.grid_remove()

        mm = self.strokes_mm()
        blocker = logic.plot_blocker(c, mm, self.half)
        idle = not self.plotting and not self.jogging
        ready = c.connected and idle
        self.btn_connect.config(text="Disconnect" if c.connected else "Connect",
                                state="normal" if idle else "disabled")
        for b in self.jog_buttons:       # stay live while held
            b.config(state="normal" if c.connected and not self.plotting
                     else "disabled")
        for b in self.goto_buttons:
            b.config(state="normal" if ready and c.origin_set else "disabled")
        for b in [self.btn_origin, self.btn_pen_up,
                  self.btn_pen_down, self.btn_change,
                  self.btn_pen_setup, self.btn_calibrate]:
            b.config(state="normal" if ready else "disabled")
        self.btn_plot.config(state="normal" if idle and blocker is None else "disabled")
        self.btn_pause.config(state="normal" if self.plotting else "disabled",
                              text="Resume" if self.paused else "Pause")
        self.btn_svg.config(state="normal" if mm and idle else "disabled")
        if idle:
            self.status.config(text=blocker or "Ready to plot.")
        self._draw_preview(mm)
        self._show_info(mm)

    def _draw_preview(self, mm):
        cv = self.canvas
        cv.delete("all")
        k = PX_PER_MM
        ox = 10 + LETTER_MM[0] * k / 2
        oy = 10 + LETTER_MM[1] * k / 2

        def px(x, y):
            return ox + x * k, oy - y * k

        cv.create_rectangle(*px(-LETTER_MM[0] / 2, LETTER_MM[1] / 2),
                            *px(LETTER_MM[0] / 2, -LETTER_MM[1] / 2),
                            fill="white", outline="#999")
        hx, hy = self.half
        cv.create_rectangle(*px(-hx, hy), *px(hx, -hy), outline="#9bd",
                            dash=(4, 3))
        cv.create_line(*px(-4, 0), *px(4, 0), fill="#c33")
        cv.create_line(*px(0, -4), *px(0, 4), fill="#c33")
        greyed = bool(self.result and self.result.get("error"))
        for s in mm:
            for a, b in zip(s, s[1:]):
                bad = not (logic.inside(a, self.half) and logic.inside(b, self.half))
                colour = "red" if bad else ("#999" if greyed else "black")
                cv.create_line(*px(*a), *px(*b), fill=colour,
                               width=2 if bad else 1)

    def _show_info(self, mm):
        if self.result is None:
            self.info.config(text="")
            return
        w, h = logic.size_mm(mm)
        secs = logic.estimate_seconds(mm, self.config["draw_feed"],
                                      self.config["travel_feed"],
                                      self.config["servo_wait_s"])
        lines = ["%d strokes, %.0f x %.0f mm at %d%%" % (len(mm), w, h, self._scale()),
                 "Estimated time: %s" % logic.format_time(secs)]
        lines += ["Warning: " + x for x in self.result.get("warnings", [])]
        err = logic.error_text(self.result.get("error"))
        if err:
            lines.append("ERROR: " + err)
        self.info.config(text="\n".join(lines))

    # ---- helpers used by the wizards ----------------------------------

    def save_setting(self, **values):
        self.raw_config.update(values)
        self.config.update(values)
        save_config(self.raw_config)

    def mark_pen_setup(self):
        today = datetime.date.today().isoformat()
        self.save_setting(pen_setup_done=today)
        self.check.pen_setup_done = today
        self.refresh()

    def mark_calibrated(self):
        today = datetime.date.today().isoformat()
        self.save_setting(calibrated=today)
        self.check.calibrated = today
        self.refresh()

    def _try(self, action, *args):
        """Run a backend action from a button; show problems in a dialog."""
        try:
            action(*args)
        except PlotterError as e:
            messagebox.showerror("Plotter", str(e), parent=self.root)
        self._sync_from_backend()
        self.refresh()

    # ---- buttons --------------------------------------------------------

    def on_connect(self):
        if self.check.connected:
            self.backend.close()
            self._sync_from_backend()
            self.refresh()
            return
        self.status.config(text="Connecting...")
        self.root.update_idletasks()
        self._try(self.backend.connect, self.port)

    def on_jog(self, dx, dy):
        step = self.jog_step.get()
        self._try(self.backend.jog, dx * step, dy * step)

    def on_jog_press(self, dx, dy):
        # bindings fire even on a greyed-out button, so check here
        if not self.check.connected or self.plotting or self.jogging:
            return
        self._jog_held = True
        self._jog_click = (dx, dy)
        self._jog_timer = self.root.after(
            300, lambda: self._start_hold_jog(dx, dy))

    def on_jog_release(self):
        self._jog_held = False         # a running hold-jog stops on this
        if self._jog_timer is not None:
            # let go before the hold started: a normal one-step click
            self.root.after_cancel(self._jog_timer)
            self._jog_timer = None
            dx, dy = self._jog_click
            self.on_jog(dx, dy)

    def _start_hold_jog(self, dx, dy):
        self._jog_timer = None
        if not self._jog_held:
            return
        self._run_move(self.backend.jog_hold, dx, dy, lambda: self._jog_held)

    def on_goto(self, fx, fy):
        """Travel to the origin (0, 0) or a corner of the drawable area."""
        if self.plotting or self.jogging or not self.backend.origin_set:
            return
        x, y = fx * self.half[0], fy * self.half[1]
        feed = self.config["travel_feed"]

        def go():
            self.backend.pen(False)
            self.backend.move(x, y, feed)
            self.backend.wait()
        self._run_move(go)

    def _run_move(self, action, *args):
        """Move the head in a worker thread, so the window (and STOP) stay
        live.  Registered as self._worker so on_stop leaves recovery to it."""
        self.jogging = True
        self.refresh()

        def work():
            try:
                action(*args)
                self.events.put(("jog_done",))
            except PlotStopped:
                try:
                    self.backend.recover()
                    self.events.put(("jog_stopped",))
                except PlotterError as e:
                    self.events.put(("jog_error", e))
            except PlotterError as e:
                self.events.put(("jog_error", e))
        self._worker = threading.Thread(target=work, daemon=True)
        self._worker.start()

    def on_set_origin(self):
        if messagebox.askokcancel(
                "Set origin",
                "Is the sheet centred on the plotter bed, and the pen over "
                "the centre of the sheet?", parent=self.root):
            self._try(self.backend.set_origin)

    def on_pen(self, down):
        self._try(self.backend.pen, down)

    def on_change_pen(self):
        if not self.backend.origin_set:
            messagebox.showinfo("Change pen", "Set the origin first, so the "
                                "head knows where the sheet is.", parent=self.root)
            return
        feed = self.config["travel_feed"]

        def go():
            self.backend.pen(False)
            self.backend.move(0.0, -self.half[1], feed)
            self.backend.wait()
            messagebox.showinfo("Change pen", "Swap the pen, then click OK.\n"
                                "The head will go back to the centre.",
                                parent=self.root)
            self.backend.move(0.0, 0.0, feed)
            self.backend.wait()
        self._try(go)

    def on_pen_setup(self):
        from dashboard_wizards import PenSetupWizard
        PenSetupWizard(self)

    def on_calibrate(self):
        from dashboard_wizards import CalibrationWizard
        CalibrationWizard(self)

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

    def load_file(self, path):
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                source = f.read()
        except OSError as e:
            messagebox.showerror("Open", str(e), parent=self.root)
            return
        self.path = path
        self.file_label.config(text=os.path.basename(path))
        self.code.config(state="normal")
        self.code.delete("1.0", "end")
        self.code.insert("1.0", source)
        self.code.config(state="disabled")
        self.status.config(text="Running the student's program...")
        self.root.config(cursor="watch")
        self.root.update_idletasks()
        try:
            self.result = logic.run_student(path,
                                            run_as=self.config.get("run_as"))
        finally:
            self.root.config(cursor="")
        self.strokes = self.result.get("strokes", [])
        self.scale.set(100)
        self.refresh()

    def on_use_text(self):
        """Plot typed text instead of a student file."""
        text = self.text.get().strip()
        if not text:
            return
        strokes, missing = logic.text_strokes(text)
        if missing:
            messagebox.showerror(
                "Text", "The plotter's font has no letter for: %s\n"
                "It has A-Z, a-z and spaces." % ", ".join(missing),
                parent=self.root)
            return
        self.path = None
        self.strokes = strokes
        self.result = {"strokes": strokes, "warnings": [], "error": None}
        self.file_label.config(text="Text: " + text)
        self.code.config(state="normal")
        self.code.delete("1.0", "end")
        self.code.insert("1.0", text)
        self.code.config(state="disabled")
        self.scale.set(100)
        self.refresh()

    def on_fit(self):
        self.scale.set(logic.fit_scale(self.strokes, self.half))
        self.refresh()

    def on_reset_scale(self):
        self.scale.set(100)
        self.refresh()

    def on_plot(self):
        mm = self.strokes_mm()
        if logic.plot_blocker(self.check, mm, self.half):
            return
        name = os.path.basename(self.path) if self.path else "drawing"
        self.start_job(mm, "Plotting " + name)

    def start_job(self, strokes_mm, label, on_done=None):
        """Plot in a worker thread; results come back through self.events."""
        self.plotting = True
        self.paused = False
        self._on_done = on_done
        self._job = {"parts": logic.stroke_estimates(
                         strokes_mm, self.config["draw_feed"],
                         self.config["travel_feed"], self.config["servo_wait_s"]),
                     "n": len(strokes_mm), "done": 0, "t0": time.time(),
                     "paused_total": 0.0, "paused_at": None}
        self.progress.config(maximum=max(1, len(strokes_mm)), value=0)
        self.status.config(text=label + "...")

        def work():
            try:
                logic.plot_strokes(
                    self.backend, strokes_mm, self.config["draw_feed"],
                    self.config["travel_feed"],
                    progress=lambda i, n: self.events.put(("progress", i, n)))
                self.events.put(("done",))
            except PlotStopped:
                try:
                    self.backend.recover()
                    self.events.put(("stopped",))
                except PlotterError as e:
                    self.events.put(("error", e))
            except PlotterError as e:
                self.events.put(("error", e))

        self._worker = threading.Thread(target=work, daemon=True)
        self._worker.start()
        self.refresh()

    def _poll(self):
        try:
            if self._hw_stop.is_set():       # Tk calls only on this thread
                self._hw_stop.clear()
                self.on_stop()
            self._handle_events()
            if self.plotting:
                self._show_timer()
            if self.jogging:
                self._show_position()
        finally:                 # keep polling even if a callback fails
            self.root.after(100, self._poll)

    def _handle_events(self):
        try:
            while True:
                ev = self.events.get_nowait()
                if ev[0] == "progress":
                    self.progress.config(value=ev[1])
                    if self._job:
                        self._job["done"] = ev[1]
                    continue
                if ev[0] in ("jog_done", "jog_error", "jog_stopped"):
                    if self._worker is not None:
                        self._worker.join(1)   # it has just put this event
                    self.jogging = False
                    self._sync_from_backend()
                    self.refresh()
                    if ev[0] == "jog_error":
                        messagebox.showerror("Plotter", str(ev[1]),
                                             parent=self.root)
                    elif ev[0] == "jog_stopped":
                        messagebox.showinfo(
                            "Stopped", "Move stopped.  The pen is up.\nSet "
                            "the origin again.", parent=self.root)
                    continue
                self.plotting = False
                self.paused = False
                self._sync_from_backend()
                callback, self._on_done = self._on_done, None
                self.refresh()
                if ev[0] == "done":
                    self.status.config(text=self._finished_text())
                    if callback:
                        callback()
                elif ev[0] == "stopped":
                    messagebox.showinfo(
                        "Stopped", "Plot stopped.  The pen is up.\nSet the "
                        "origin again before the next plot.", parent=self.root)
                else:
                    messagebox.showerror("Plotter", str(ev[1]), parent=self.root)
        except queue.Empty:
            pass

    def _active_seconds(self, now):
        """Time spent plotting, not counting pauses."""
        j = self._job
        paused = j["paused_total"]
        if j["paused_at"] is not None:
            paused += now - j["paused_at"]
        return now - j["t0"] - paused

    def _show_timer(self):
        j = self._job
        if j is None:
            return
        now = time.time()
        elapsed = logic.format_clock(now - j["t0"])
        stroke = "Stroke %d of %d" % (min(j["done"] + 1, j["n"]), j["n"])
        if self.paused:
            text = "Paused - %s - elapsed %s" % (stroke, elapsed)
        else:
            left = logic.remaining_seconds(j["parts"], j["done"],
                                           self._active_seconds(now))
            text = "%s - elapsed %s - about %s left" % (
                stroke, elapsed, logic.format_clock(left))
        self.status.config(text=text)

    def _finished_text(self):
        j = self._job
        if j is None:
            return "Finished."
        return "Finished in %s (estimated %s)" % (
            logic.format_clock(time.time() - j["t0"]),
            logic.format_clock(sum(j["parts"])))

    def on_pause(self):
        if not self.plotting:
            return
        try:
            if self.paused:
                self.backend.resume()
            else:
                self.backend.pause()
            self.paused = not self.paused
            if self._job:
                now = time.time()
                if self.paused:
                    self._job["paused_at"] = now
                elif self._job["paused_at"] is not None:
                    self._job["paused_total"] += now - self._job["paused_at"]
                    self._job["paused_at"] = None
        except PlotterError as e:
            messagebox.showerror("Plotter", str(e), parent=self.root)
        self.refresh()

    def on_stop(self):
        if not self.backend.connected:
            return
        try:
            self.backend.stop()
            # Recover here unless a running plot thread will do it.  Don't go
            # by self.plotting: it lags the thread by up to one poll.
            worker = self._worker
            if worker is None or not worker.is_alive():
                self.backend.recover()
        except PlotterError as e:
            messagebox.showerror("Plotter", str(e), parent=self.root)
        self.paused = False
        self._sync_from_backend()
        self.refresh()

    def on_save_svg(self):
        base = os.path.splitext(os.path.basename(self.path or "drawing"))[0]
        path = filedialog.asksaveasfilename(
            parent=self.root, defaultextension=".svg",
            initialfile=base + ".svg", filetypes=[("SVG drawing", "*.svg")])
        if not path:
            return
        with open(path, "w", encoding="utf-8") as f:
            f.write(logic.svg_text(self.strokes_mm()))
        self.status.config(text="Saved " + path)

    def on_close(self):
        if self.plotting:
            if not messagebox.askyesno("Quit", "A plot is running.  Stop the "
                                       "plot and quit?", parent=self.root):
                return
            try:
                self.backend.stop()
            except PlotterError:
                pass
        elif self.backend.connected:
            try:
                self.backend.pen(False)
            except PlotterError:
                pass
        self.backend.close()
        self.root.destroy()


def kiosk(root):
    """Fill the whole (virtual) screen - used on the Raspberry Pi.
    Fullscreen, so no title bar pushes STOP off the bottom (and there is
    no close button to reset the AX4 by accident)."""
    root.attributes("-fullscreen", True)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    root = tk.Tk()
    if "--kiosk" in argv:
        kiosk(root)
    Dashboard(root)
    root.mainloop()


if __name__ == "__main__":
    main()
