"""
Smoke tests: build the dashboard window against the fake port and press a
few buttons.  No plotter, but needs a display (fine on the teacher laptop).

    python tests/test_dashboard_smoke.py
"""

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
            root.destroy()

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
        finally:
            root.destroy()

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
            root.destroy()


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
            root.destroy()

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
            root.destroy()


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
            root.destroy()

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
            root.destroy()

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
            root.destroy()

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
            root.destroy()


if __name__ == "__main__":
    unittest.main()
