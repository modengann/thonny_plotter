"""
Smoke tests: build the dashboard window against the fake port and press a
few buttons.  No plotter, but needs a display (fine on the teacher laptop).

    python tests/test_dashboard_smoke.py
"""

import gc
import os
import sys
import time
import tkinter as tk
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

import dashboard
from fake_grbl import FakeGrbl
from grbl_backend import GrblBackend

SAMPLES = os.path.join(HERE, "samples")


def make(fake, save=False):
    root = tk.Tk()
    root.withdraw()
    b = GrblBackend({}, opener=lambda port: fake)
    d = dashboard.Dashboard(root, backend=b)
    d.port = "COM99"                     # never look for the real plotter
    if not save:
        d.save_setting = lambda **v: d.config.update(v)   # keep the real file
    return root, d


def close(root):
    """Destroy the window and free its Tk variables now, on this thread.

    Left to the garbage collector, they can be freed later from a jog or
    plot thread, which Tk refuses ("main thread is not in main loop").
    """
    root.destroy()
    gc.collect()


def pump(root, until, seconds=10):
    end = time.time() + seconds
    while time.time() < end and not until():
        root.update()
        time.sleep(0.02)


class TestDashboard(unittest.TestCase):

    def test_starts_with_plot_disabled(self):
        root, d = make(FakeGrbl())
        try:
            self.assertEqual(str(d.btn_plot["state"]), "disabled")
            self.assertIn("Connect", d.status["text"])
        finally:
            close(root)

    def test_connect_origin_open_and_plot(self):
        fake = FakeGrbl()
        root, d = make(fake)
        try:
            d.check.pen_setup_done = "2026-10-04"
            d.on_connect()
            self.assertTrue(d.check.connected)
            d.backend.set_origin()
            d.check.origin_set = True
            d.load_file(os.path.join(SAMPLES, "square.py"))
            self.assertEqual(str(d.btn_plot["state"]), "normal")
            d.on_plot()
            pump(root, lambda: not d.plotting)
            self.assertFalse(d.plotting)
            self.assertIn("G1 X25.000 Y0.000 F1500", fake.sent)
            self.assertIn("Finished in", d.status["text"])
            self.assertIn("estimated", d.status["text"])
        finally:
            close(root)

    def test_too_big_drawing_blocks_plot_until_fit(self):
        root, d = make(FakeGrbl())
        try:
            d.check.pen_setup_done = "x"
            d.on_connect()
            d.backend.set_origin()
            d.check.origin_set = True
            d.load_file(os.path.join(SAMPLES, "square.py"))
            d.scale.set(1000)
            d.refresh()
            self.assertEqual(str(d.btn_plot["state"]), "disabled")
            d.on_fit()
            self.assertEqual(str(d.btn_plot["state"]), "normal")
        finally:
            close(root)


class TestReviewFixes(unittest.TestCase):

    def test_stop_after_worker_finished_still_recovers(self):
        fake = FakeGrbl()
        root, d = make(fake)
        try:
            d.on_connect()
            d.plotting = True        # "done" queued but not yet polled
            d._worker = None         # no thread left to call recover()
            fake.sent.clear()
            d.on_stop()
            self.assertIn("$X", fake.sent)
            self.assertFalse(d.backend._stopping)
        finally:
            close(root)

    def test_poll_survives_a_failing_callback(self):
        fake = FakeGrbl()
        root, d = make(fake)
        try:
            d.on_connect()
            d.backend.set_origin()

            def broken():
                raise tk.TclError("wizard window was closed")
            d.start_job([[(0, 0), (5, 0)]], "test", on_done=broken)
            pump(root, lambda: not d.plotting)
            d.start_job([[(0, 0), (5, 0)]], "again")
            pump(root, lambda: not d.plotting)
            self.assertFalse(d.plotting)       # second job was noticed
        finally:
            close(root)


class TestTimerDisplay(unittest.TestCase):

    def test_status_shows_elapsed_and_remaining_while_plotting(self):
        root, d = make(FakeGrbl(read_delay=0.01))
        try:
            d.check.pen_setup_done = "x"
            d.on_connect()
            d.backend.set_origin()
            d.check.origin_set = True
            d.load_file(os.path.join(SAMPLES, "square.py"))
            d.on_plot()
            seen = []
            pump(root, lambda: (seen.append(d.status["text"]) and False)
                 or not d.plotting)
            self.assertTrue(any("elapsed" in t and "left" in t for t in seen),
                            seen[:5])
        finally:
            close(root)


class TestHoldToJog(unittest.TestCase):

    def test_quick_click_is_one_step(self):
        fake = FakeGrbl()
        root, d = make(fake)
        try:
            d.on_connect()
            fake.sent.clear()
            d.on_jog_press(1, 0)
            d.on_jog_release()
            pump(root, lambda: not d.jogging)
            self.assertIn("G1 X10.000 Y0.000 F1500", fake.sent)
        finally:
            close(root)

    def test_holding_moves_continuously_until_release(self):
        fake = FakeGrbl(read_delay=0.02)   # replies take time, like a real port
        root, d = make(fake)
        try:
            d.on_connect()
            fake.sent.clear()
            d.on_jog_press(0, 1)
            pump(root, lambda: False, seconds=0.8)      # hold
            self.assertTrue(d.jogging)
            d.on_jog_release()
            pump(root, lambda: not d.jogging)
            moves = [l for l in fake.sent if l.startswith("G1")]
            self.assertGreaterEqual(len(moves), 2)
            self.assertLess(len(moves), 33)       # stopped by release, not cap
            self.assertTrue(all(l == "G1 X0.000 Y3.000 F900" for l in moves))
        finally:
            close(root)


class TestPositionReadout(unittest.TestCase):

    def test_shows_head_position_from_the_origin(self):
        root, d = make(FakeGrbl())
        try:
            self.assertIn("---", d.pos_label["text"])
            d.on_connect()
            d.backend.jog(30, 40)
            d._try(d.backend.set_origin)
            self.assertIn("X     0.0  Y     0.0", d.pos_label["text"])
            d.on_jog_press(-1, 0)
            d.on_jog_release()
            pump(root, lambda: not d.jogging)
            self.assertIn("X   -10.0  Y     0.0", d.pos_label["text"])
            self.assertIn("from origin", d.pos_label["text"])
        finally:
            close(root)


class TestGoTo(unittest.TestCase):

    def test_goto_needs_an_origin(self):
        root, d = make(FakeGrbl())
        try:
            d.on_connect()
            self.assertTrue(all(str(b["state"]) == "disabled"
                                for b in d.goto_buttons))
            d._try(d.backend.set_origin)
            self.assertTrue(all(str(b["state"]) == "normal"
                                for b in d.goto_buttons))
        finally:
            close(root)

    def test_goto_corner_then_origin(self):
        fake = FakeGrbl()
        root, d = make(fake)
        try:
            d.on_connect()
            d._try(d.backend.set_origin)
            hx, hy = d.half
            d.on_goto(-1, 1)
            pump(root, lambda: not d.jogging)
            self.assertIn("G1 X%.3f Y%.3f F3000" % (-hx, hy), fake.sent)
            self.assertIn("X  %6.1f  Y  %6.1f" % (-hx, hy), d.pos_label["text"])
            d.on_goto(0, 0)
            pump(root, lambda: not d.jogging)
            self.assertEqual(fake.sent[-2], "G1 X0.000 Y0.000 F3000")
            self.assertIn("X     0.0  Y     0.0", d.pos_label["text"])
        finally:
            close(root)


class TestTextBox(unittest.TestCase):

    def test_typed_text_becomes_a_plottable_drawing(self):
        fake = FakeGrbl()
        root, d = make(fake)
        try:
            d.check.pen_setup_done = "x"
            d.on_connect()
            d.backend.set_origin()
            d.check.origin_set = True
            d.text.set("Gabe Cahill")
            d.on_use_text()
            self.assertTrue(d.strokes)
            self.assertEqual(str(d.btn_plot["state"]), "normal")
            d.on_plot()
            pump(root, lambda: not d.plotting)
            self.assertFalse(d.plotting)
        finally:
            close(root)

    def test_unknown_characters_are_explained(self):
        root, d = make(FakeGrbl())
        shown = []
        saved = dashboard.messagebox.showerror
        dashboard.messagebox.showerror = lambda *a, **k: shown.append(a)
        try:
            d.text.set("Room 12")
            d.on_use_text()
            self.assertEqual(d.strokes, [])
            self.assertIn("1, 2", shown[0][1])
        finally:
            dashboard.messagebox.showerror = saved
            close(root)


class TestWizards(unittest.TestCase):

    def test_pen_setup_lifts_then_goes_to_touch_position(self):
        fake = FakeGrbl()
        root, d = make(fake)
        try:
            d.on_connect()
            fake.sent.clear()
            import dashboard_wizards
            w = dashboard_wizards.PenSetupWizard(d)
            self.assertIn("M5", fake.sent)
            w.s2()
            w.s3()
            self.assertIn("M3 S60", fake.sent)
            w.destroy()
        finally:
            close(root)

    def test_pen_setup_test_needs_an_origin(self):
        root, d = make(FakeGrbl())
        try:
            d.on_connect()
            import dashboard_wizards
            w = dashboard_wizards.PenSetupWizard(d)
            w.s4()
            self.assertIn("Set origin here", w.text["text"])
            w.destroy()
        finally:
            close(root)

    def test_pen_setup_solid_lines_ticks_the_checklist(self):
        root, d = make(FakeGrbl())
        try:
            d.on_connect()
            d.check.pen_setup_done = None
            import dashboard_wizards
            w = dashboard_wizards.PenSetupWizard(d)
            w.done()
            self.assertTrue(d.check.pen_setup_done)
            w.destroy()
        finally:
            close(root)

    def test_calibration_applies_the_average_to_both_axes(self):
        fake = FakeGrbl(replies={"$$": ["$100=80.000 (x, step/mm)",
                                        "$101=80.000 (y, step/mm)", "ok"]})
        root, d = make(fake)
        try:
            d.on_connect()
            d.backend.set_origin()
            d.check.origin_set = True
            d.check.pen_setup_done = "x"
            import dashboard_wizards
            w = dashboard_wizards.CalibrationWizard(d)
            w.s2()
            w.vx.set("149")
            w.vy.set("149")
            w.calc()
            fake.sent.clear()
            w.apply()
            self.assertEqual(fake.sent, ["$100=80.537", "$101=80.537"])
            self.assertTrue(d.check.calibrated)
            self.assertFalse(d.backend.origin_set)
            w.destroy()
        finally:
            close(root)


if __name__ == "__main__":
    unittest.main()
