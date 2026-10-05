"""
Offline tests for plotter.py -- no printer, no pyserial needed.

Run from the project root:

    python tests/test_exports.py

These check the part that is easy to get wrong: that drawing really
records strokes, and that the SVG and G-code contain those strokes with
coordinates that land on the paper.
"""

import os
import re
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import turtle
from plotter import Plotter


def make_plotter(**kw):
    """A Plotter with the screen animation turned off, for fast tests."""
    turtle.Screen().tracer(0)
    kw.setdefault("show_paper", False)
    p = Plotter(**kw)
    p.hideturtle()
    return p


class TestStrokeRecording(unittest.TestCase):

    def test_pen_down_move_records_a_stroke(self):
        t = make_plotter()
        t.penup()
        t.goto(0, 0)
        t.pendown()
        t.forward(100)
        self.assertEqual(len(t.strokes), 1)
        self.assertEqual(len(t.strokes[0]), 2)

    def test_later_points_land_in_the_same_stroke(self):
        """The bug was that self.strokes stayed empty; guard both halves."""
        t = make_plotter()
        t.penup()
        t.goto(0, 0)
        t.pendown()
        for _ in range(4):
            t.forward(100)
            t.left(90)
        self.assertEqual(len(t.strokes), 1)
        self.assertEqual(len(t.strokes[0]), 5)   # start + 4 corners

    def test_penup_starts_a_new_stroke(self):
        t = make_plotter()
        t.penup()
        t.goto(0, 0)
        t.pendown()
        t.forward(100)
        t.penup()
        t.goto(-100, -100)
        t.pendown()
        t.forward(50)
        self.assertEqual(len(t.strokes), 2)

    def test_travel_moves_are_not_recorded(self):
        t = make_plotter()
        t.penup()
        t.goto(100, 100)
        t.goto(-100, 100)
        self.assertEqual(t.strokes, [])

    def test_coordinates_are_mm_on_the_bed(self):
        t = make_plotter(paper_mm=150.0, scale=0.25, bed_mm=180.0)
        t.penup()
        t.goto(0, 0)
        t.pendown()
        t.goto(100, 0)           # 100 units * 0.25 = 25 mm right of centre
        (x0, y0), (x1, y1) = t.strokes[0]
        self.assertAlmostEqual(x0, 90.0, places=3)
        self.assertAlmostEqual(y0, 90.0, places=3)
        self.assertAlmostEqual(x1, 115.0, places=3)
        self.assertAlmostEqual(y1, 90.0, places=3)

    def test_moves_off_the_paper_are_clamped(self):
        t = make_plotter(paper_mm=150.0, scale=0.25, bed_mm=180.0)
        t.penup()
        t.goto(0, 0)
        t.pendown()
        t.goto(10000, 0)         # way off the right edge
        for (mx, my) in t.strokes[0]:
            self.assertLessEqual(mx, 165.0 + 1e-6)   # 90 + 75
            self.assertGreaterEqual(mx, 15.0 - 1e-6)


class TestExports(unittest.TestCase):

    def setUp(self):
        self.t = make_plotter(paper_mm=150.0, scale=0.25, bed_mm=180.0)
        self.t.penup()
        self.t.goto(-200, -200)
        self.t.pendown()
        for _ in range(4):           # a 50 mm square
            self.t.forward(200)
            self.t.left(90)
        self.t.penup()
        self.t.goto(100, 100)
        self.t.pendown()
        self.t.forward(100)          # a separate second stroke
        self.t.penup()
        self.dir = tempfile.mkdtemp()

    def test_svg_has_one_path_per_stroke(self):
        path = os.path.join(self.dir, "out.svg")
        self.t.save_svg(path)
        with open(path, encoding="utf-8") as f:
            svg = f.read()
        self.assertEqual(svg.count("<path"), len(self.t.strokes))
        self.assertIn('viewBox="0 0 150 150"', svg)

    def test_svg_coordinates_are_inside_the_paper(self):
        path = os.path.join(self.dir, "out.svg")
        self.t.save_svg(path)
        with open(path, encoding="utf-8") as f:
            svg = f.read()
        nums = [float(n) for n in re.findall(r"-?\d+\.\d+", svg)]
        self.assertTrue(nums, "no coordinates in the SVG")
        for n in nums:
            self.assertGreaterEqual(n, -0.001)
            self.assertLessEqual(n, 150.001)

    def test_gcode_has_moves_and_pen_lifts(self):
        path = os.path.join(self.dir, "out.gcode")
        self.t.save_gcode(path)
        with open(path, encoding="utf-8") as f:
            g = f.read().splitlines()
        moves = [l for l in g if l.startswith("G1 X")]
        self.assertGreaterEqual(len(moves), 8)
        # one pen-down and one pen-up Z move per stroke
        downs = [l for l in g if l.startswith("G1 Z%.3f" % self.t.pen_down_z)]
        self.assertEqual(len(downs), len(self.t.strokes))
        self.assertIn("M84 ; motors off", g)
        self.assertTrue(any(l.startswith("M104 S0") for l in g), "heater not off")

    def test_gcode_xy_stays_on_the_bed(self):
        path = os.path.join(self.dir, "out.gcode")
        self.t.save_gcode(path)
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines()
        for line in lines:
            m = re.match(r"G1 X(-?\d+\.\d+) Y(-?\d+\.\d+)", line)
            if m:
                x, y = float(m.group(1)), float(m.group(2))
                self.assertGreaterEqual(x, 0.0)
                self.assertLessEqual(x, 180.0)
                self.assertGreaterEqual(y, 0.0)
                self.assertLessEqual(y, 180.0)

    def test_finish_is_safe_with_no_printer(self):
        self.t.finish()          # must not raise


if __name__ == "__main__":
    unittest.main(verbosity=2, exit=False)
