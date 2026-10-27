"""
Tests for dashboard_logic.py -- no window, no plotter.

    python tests/test_dashboard_logic.py
"""

import os
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

import dashboard_logic as logic
from fake_grbl import FakeGrbl
from grbl_backend import GrblBackend, drawable_area

AREA = drawable_area()                   # (0, 259.4, -195.9, 0): top-left
UP = drawable_area("bottom_left")        # (0, 259.4, 0, 195.9)
SAMPLES = os.path.join(HERE, "samples")


class TestScale(unittest.TestCase):

    def test_100_percent_is_one_mm_per_step(self):
        self.assertEqual(logic.to_mm([[(0, 0), (100, -40)]], 100),
                         [[(0.0, 0.0), (100.0, -40.0)]])

    def test_200_percent_doubles(self):
        self.assertEqual(logic.to_mm([[(0, 0), (100, 0)]], 200)[0][1], (200.0, 0.0))

    def test_fits_and_inside(self):
        self.assertTrue(logic.fits([[(0, 0), (259.4, -195.9)]], AREA))
        self.assertFalse(logic.fits([[(0, 0), (260, 0)]], AREA))
        self.assertFalse(logic.inside((0, 1), AREA))      # above the origin
        self.assertTrue(logic.inside((0, 1), UP))
        self.assertFalse(logic.inside((-1, 10), UP))

    def test_fit_scale_uses_the_tighter_axis(self):
        # x 600 steps -> 259.4 / 600 = 43.2%; y -100 -> 195.9%
        self.assertEqual(logic.fit_scale([[(0, 0), (600, -100)]], AREA), 43)

    def test_fit_scale_result_actually_fits(self):
        strokes = [[(3, -271), (517, -38)]]
        pct = logic.fit_scale(strokes, AREA)
        self.assertTrue(logic.fits(logic.to_mm(strokes, pct), AREA))
        self.assertFalse(logic.fits(logic.to_mm(strokes, pct + 1), AREA))

    def test_fit_scale_is_capped(self):
        self.assertEqual(logic.fit_scale([[(0, 0), (1, 0)]], AREA), logic.MAX_SCALE)

    def test_wrong_side_of_the_origin_cannot_fit(self):
        up_right = [[(0, 0), (100, 0), (100, 100)]]
        self.assertTrue(logic.wrong_side(up_right, AREA))
        self.assertIsNone(logic.fit_scale(up_right, AREA))
        self.assertFalse(logic.wrong_side(up_right, UP))
        self.assertEqual(logic.fit_scale(up_right, UP), 195)

    def test_student_portrait_fits_at_its_own_size(self):
        # 40 x 27 cells of 5 mm from 0,0, drawn down and to the right
        grid = [[(0, 0), (200, 0), (200, -135), (0, -135), (0, 0)]]
        self.assertTrue(logic.fits(logic.to_mm(grid, 100), AREA))
        self.assertEqual(logic.fit_scale(grid, AREA), 129)

    def test_size(self):
        self.assertEqual(logic.size_mm([[(-10, 5), (30, -15)]]), (40, 20))


class TestEmpty(unittest.TestCase):

    def test_empty_drawing(self):
        self.assertEqual(logic.fit_scale([], AREA), 100)
        self.assertEqual(logic.size_mm([]), (0, 0))
        self.assertEqual(logic.estimate_seconds([], 1500, 3000), 0)
        c = logic.Checklist({"pen_setup_done": "2026-10-04"})
        c.connected = c.origin_set = True
        self.assertEqual(logic.plot_blocker(c, [], AREA),
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


class TestTimer(unittest.TestCase):

    STROKES = [[(0, 0), (25, 0)], [(25, 10), (25, 35)]]

    def test_per_stroke_estimates_add_up_to_the_total(self):
        parts = logic.stroke_estimates(self.STROKES, 1500, 3000)
        self.assertEqual(len(parts), 2)
        self.assertAlmostEqual(sum(parts),
                               logic.estimate_seconds(self.STROKES, 1500, 3000))

    def test_remaining_before_anything_is_drawn_is_the_estimate(self):
        parts = [2.0, 3.0]
        self.assertAlmostEqual(logic.remaining_seconds(parts, 0, 0.0), 5.0)

    def test_remaining_is_corrected_by_actual_speed(self):
        # first stroke estimated 2 s but took 3 s: the rest is 50% slower
        self.assertAlmostEqual(logic.remaining_seconds([2.0, 3.0], 1, 3.0), 4.5)

    def test_nothing_remaining_when_done(self):
        self.assertEqual(logic.remaining_seconds([2.0, 3.0], 2, 6.0), 0)

    def test_clock_format(self):
        self.assertEqual(logic.format_clock(0), "0:00")
        self.assertEqual(logic.format_clock(65.4), "1:05")
        self.assertEqual(logic.format_clock(3725), "62:05")


class TestChecklist(unittest.TestCase):

    def test_fresh_session_needs_connect_and_origin(self):
        c = logic.Checklist({"pen_setup_done": "2026-10-04", "calibrated": None})
        self.assertFalse(c.can_plot)
        self.assertEqual(c.problems(), [
            "Connect to the plotter.",
            "Set the origin (pen 10 mm in from the top-left corner of "
            "the sheet)."])

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
        self.assertEqual(logic.plot_blocker(c, [[(0, 0), (300, 0)]], AREA),
                         "Drawing doesn't fit - use Fit to paper or a smaller scale.")
        self.assertIsNone(logic.plot_blocker(c, [[(0, 0), (20, 0)]], AREA))

    def test_blocker_for_wrong_side_of_origin(self):
        c = logic.Checklist({"pen_setup_done": "x"})
        c.connected = c.origin_set = True
        msg = logic.plot_blocker(c, [[(0, 0), (20, 30)]], AREA)
        self.assertIn("above", msg)
        self.assertIn("top-left origin", msg)


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
        s = logic.calibration_strokes(AREA)
        self.assertTrue(logic.fits(s, AREA))
        self.assertTrue(logic.fits(logic.calibration_strokes(UP), UP))
        corner, x_end, y_end = s[0][1], s[0][0], s[0][2]
        self.assertEqual(x_end[0] - corner[0], 150)
        self.assertEqual(y_end[1] - corner[1], 150)

    def test_zigzag_is_three_separate_strokes_40mm_wide(self):
        z = logic.zigzag_strokes(AREA)
        self.assertTrue(logic.fits(z, AREA))
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

    def test_origin_is_10mm_in_from_the_top_left(self):
        text = logic.svg_text([[(0, 0), (10, -10)]], AREA, 10)
        self.assertIn('width="279.4mm"', text)
        self.assertIn('height="215.9mm"', text)
        self.assertIn("M 10.000,10.000 L 20.000,20.000", text)

    def test_bottom_left_origin_in_svg(self):
        text = logic.svg_text([[(0, 0)]], UP, 10)
        self.assertIn("M 10.000,205.900", text)


class TestText(unittest.TestCase):

    def test_text_starts_at_the_origin_and_goes_into_the_sheet(self):
        strokes, missing = logic.text_strokes("Kim", AREA)
        self.assertEqual(missing, [])
        xs = [x for s in strokes for x, _ in s]
        ys = [y for s in strokes for _, y in s]
        self.assertAlmostEqual(min(xs), 0)
        self.assertAlmostEqual(max(ys), 0)
        self.assertTrue(logic.fits(strokes, AREA))
        up, _ = logic.text_strokes("Kim", UP)
        self.assertAlmostEqual(min(y for s in up for _, y in s), 0)

    def test_capitals_are_15mm_tall_at_100_percent(self):
        strokes, _ = logic.text_strokes("I", AREA)
        self.assertAlmostEqual(logic.size_mm(logic.to_mm(strokes, 100))[1], 15)

    def test_unknown_characters_are_listed_once(self):
        strokes, missing = logic.text_strokes("Room 12!1", AREA)
        self.assertEqual(missing, ["!", "1", "2"])
        self.assertEqual(strokes, [])

    def test_empty_text_draws_nothing(self):
        self.assertEqual(logic.text_strokes("", AREA), ([], []))

    def test_hangeul_blocks_work(self):
        strokes, missing = logic.text_strokes("김세정", AREA)
        self.assertEqual(missing, [])
        self.assertTrue(strokes)


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


class TestPortrait(unittest.TestCase):

    def test_drawing_right_is_plotter_up_and_drawing_down_is_plotter_right(self):
        self.assertEqual(logic.to_plotter((10, 0), "portrait"), (0, 10))
        self.assertEqual(logic.to_plotter((0, -10), "portrait"), (10, 0))
        self.assertEqual(logic.to_plotter((3, 4), "landscape"), (3, 4))

    def test_from_plotter_undoes_to_plotter(self):
        p = logic.to_plotter((12.5, -40), "portrait")
        self.assertEqual(logic.from_plotter(p, "portrait"), (12.5, -40))

    def test_portrait_drawing_lands_inside_the_plotter_limits(self):
        from grbl_backend import paper_mm, plotter_area
        area = drawable_area("top_left", paper_mm("portrait"))
        x0, x1, y0, y1 = area
        corners = [[(x0, y0), (x1, y0), (x1, y1), (x0, y1)]]
        out = logic.strokes_to_plotter(corners, "portrait")
        limits = plotter_area("top_left", "portrait")
        self.assertTrue(all(logic.inside(p, limits) for p in out[0]))

    def test_origin_corner_names(self):
        self.assertEqual(logic.plotter_corner("top_left", "portrait"), "bottom-left")
        self.assertEqual(logic.plotter_corner("bottom_left", "portrait"), "bottom-right")
        self.assertEqual(logic.plotter_corner("top_left", "landscape"), "top-left")


if __name__ == "__main__":
    unittest.main()
