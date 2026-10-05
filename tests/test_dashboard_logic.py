"""
Tests for dashboard_logic.py -- no window, no plotter.

    python tests/test_dashboard_logic.py
"""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

import dashboard_logic as logic
from fake_grbl import FakeGrbl
from grbl_backend import GrblBackend, usable_half

HALF = usable_half()                     # (129.7, 97.95)
SAMPLES = os.path.join(HERE, "samples")


class TestScale(unittest.TestCase):

    def test_100_percent_is_quarter_mm_per_step(self):
        self.assertEqual(logic.to_mm([[(0, 0), (100, -40)]], 100),
                         [[(0.0, 0.0), (25.0, -10.0)]])

    def test_200_percent_doubles(self):
        self.assertEqual(logic.to_mm([[(0, 0), (100, 0)]], 200)[0][1], (50.0, 0.0))

    def test_fits_and_inside(self):
        self.assertTrue(logic.fits([[(0, 0), (129.7, 97.95)]], HALF))
        self.assertFalse(logic.fits([[(0, 0), (130, 0)]], HALF))
        self.assertFalse(logic.inside((0, -98), HALF))

    def test_fit_scale_uses_the_tighter_axis(self):
        # x extent 600 steps -> 129.7 / (600*0.25) = 86.4%; y 100 -> 391%
        self.assertEqual(logic.fit_scale([[(-600, 0), (600, 100)]], HALF), 86)

    def test_fit_scale_result_actually_fits(self):
        strokes = [[(-333, -271), (517, 389)]]
        pct = logic.fit_scale(strokes, HALF)
        self.assertTrue(logic.fits(logic.to_mm(strokes, pct), HALF))
        self.assertFalse(logic.fits(logic.to_mm(strokes, pct + 1), HALF))

    def test_fit_scale_is_capped(self):
        self.assertEqual(logic.fit_scale([[(0, 0), (1, 0)]], HALF), logic.MAX_SCALE)

    def test_size(self):
        self.assertEqual(logic.size_mm([[(-10, 5), (30, -15)]]), (40, 20))


class TestEmpty(unittest.TestCase):

    def test_empty_drawing(self):
        self.assertEqual(logic.fit_scale([], HALF), 100)
        self.assertEqual(logic.size_mm([]), (0, 0))
        self.assertEqual(logic.estimate_seconds([], 1500, 3000), 0)
        c = logic.Checklist({"pen_setup_done": "2026-10-04"})
        c.connected = c.origin_set = True
        self.assertEqual(logic.plot_blocker(c, [], HALF),
                         "Nothing to plot - open a student file first.")


class TestTime(unittest.TestCase):

    def test_one_line(self):
        # 25 mm at 25 mm/s = 1 s, + 0.05 per segment, + 2 x 0.3 pen,
        # + 25 mm back to the origin at 50 mm/s = 0.5 s
        t = logic.estimate_seconds([[(0, 0), (25, 0)]], 1500, 3000)
        self.assertAlmostEqual(t, 2.15)

    def test_format(self):
        self.assertEqual(logic.format_time(42.4), "42 s")
        self.assertEqual(logic.format_time(65), "1 min 05 s")


class TestChecklist(unittest.TestCase):

    def test_fresh_session_needs_connect_and_origin(self):
        c = logic.Checklist({"pen_setup_done": "2026-10-04", "calibrated": None})
        self.assertFalse(c.can_plot)
        self.assertEqual(c.problems(), [
            "Connect to the plotter.",
            "Set the origin (head over the centre of the sheet)."])

    def test_pen_setup_required(self):
        c = logic.Checklist({})
        c.connected = c.origin_set = True
        self.assertEqual(c.problems(), ["Run Pen setup."])

    def test_calibration_does_not_block_but_shows_banner(self):
        c = logic.Checklist({"pen_setup_done": "x", "calibrated": None})
        c.connected = c.origin_set = True
        self.assertTrue(c.can_plot)
        self.assertIn("NOT CALIBRATED", c.banner)
        c.calibrated = "2026-11-01"
        self.assertEqual(c.banner, "")

    def test_blocker_for_off_paper(self):
        c = logic.Checklist({"pen_setup_done": "x"})
        c.connected = c.origin_set = True
        self.assertEqual(logic.plot_blocker(c, [[(0, 0), (200, 0)]], HALF),
                         "Drawing doesn't fit - use Fit to paper or a smaller scale.")
        self.assertIsNone(logic.plot_blocker(c, [[(0, 0), (20, 0)]], HALF))


class TestCalibration(unittest.TestCase):

    def test_short_lines_mean_more_steps(self):
        new, differ = logic.calibration_result(80.0, 149.0, 149.0)
        self.assertAlmostEqual(new, 80.537, places=3)
        self.assertFalse(differ)

    def test_x_and_y_are_averaged_and_flagged(self):
        new, differ = logic.calibration_result(80.0, 147.0, 151.0)
        self.assertAlmostEqual(new, round((80 * 150 / 147 + 80 * 150 / 151) / 2, 3))
        self.assertTrue(differ)

    def test_silly_measurements_are_refused(self):
        with self.assertRaises(ValueError):
            logic.calibration_result(80.0, 15.0, 150.0)

    def test_calibration_l_fits_and_is_150mm(self):
        s = logic.calibration_strokes()
        self.assertTrue(logic.fits(s, HALF))
        corner, x_end, y_end = s[0][1], s[0][0], s[0][2]
        self.assertEqual(x_end[0] - corner[0], 150)
        self.assertEqual(y_end[1] - corner[1], 150)

    def test_zigzag_is_three_separate_strokes_40mm_wide(self):
        z = logic.zigzag_strokes()
        self.assertEqual(len(z), 3)
        self.assertEqual(logic.size_mm(z)[0], 40)


class TestPlotStrokes(unittest.TestCase):

    def test_order_travel_wait_pen_draw(self):
        fake = FakeGrbl()
        b = GrblBackend({}, opener=lambda port: fake)
        b.connect("COM99")
        b.set_origin()
        fake.sent.clear()
        seen = []
        logic.plot_strokes(b, [[(10, 0), (20, 0)]], 1500, 3000,
                           progress=lambda i, n: seen.append((i, n)))
        self.assertEqual(fake.sent, [
            "G1 X10.000 Y0.000 F3000", "G4 P0",          # travel, arrive
            "G4 P0", "M3 S80", "G4 P0.30",               # pen down
            "G1 X20.000 Y0.000 F1500", "G4 P0",          # draw, finish line
            "G4 P0", "M5", "G4 P0.30",                   # pen up
            "G1 X0.000 Y0.000 F3000", "G4 P0"])          # home to origin
        self.assertEqual(seen, [(1, 1)])


class TestSvg(unittest.TestCase):

    def test_centre_maps_to_middle_of_sheet(self):
        text = logic.svg_text([[(0, 0), (10, 10)]])
        self.assertIn('width="279.4mm"', text)
        self.assertIn("M 139.700,107.950 L 149.700,97.950", text)


class TestRunStudent(unittest.TestCase):

    def test_good_file(self):
        r = logic.run_student(os.path.join(SAMPLES, "square.py"))
        self.assertIsNone(r["error"])
        self.assertEqual(len(r["strokes"]), 1)

    def test_endless_loop_is_stopped(self):
        path = os.path.join(SAMPLES, "forever.py")
        r = logic.run_student(path, timeout=3)
        self.assertEqual(r["error"]["type"], "Timeout")
        self.assertIn("too long", logic.error_text(r["error"]))

    def test_error_text(self):
        self.assertEqual(logic.error_text(None), "")
        self.assertEqual(
            logic.error_text({"type": "NameError", "line": 4,
                              "message": "name 'forwad' is not defined"}),
            "Line 4: NameError: name 'forwad' is not defined")


if __name__ == "__main__":
    unittest.main()
