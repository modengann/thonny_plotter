"""
Offline tests: the Plotter turtle driving the AX4 through GrblBackend.

    python tests/test_plotter_grbl.py
"""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

import turtle
import grbl_backend
from fake_grbl import FakeGrbl
from grbl_backend import GrblBackend
from plotter import Plotter, PlotterError

CFG = {"backend": "grbl", "draw_feed": 1500, "travel_feed": 3000}


def grbl_plotter(fake):
    turtle.Screen().tracer(0)
    p = Plotter(show_paper=False, config=CFG)
    p.hideturtle()
    p.grbl = GrblBackend(CFG, opener=lambda port: fake)
    p.grbl.connect("COM99")
    p.prepare()
    fake.sent.clear()
    return p


class TestPlotterOnGrbl(unittest.TestCase):

    def test_backend_name_comes_from_config(self):
        turtle.Screen().tracer(0)
        self.assertEqual(Plotter(show_paper=False, config=CFG).backend_name, "grbl")
        self.assertEqual(Plotter(show_paper=False, config={}).backend_name, "mini")

    def test_prepare_sets_the_origin_without_moving(self):
        fake = FakeGrbl()
        p = grbl_plotter(fake)
        self.assertTrue(p.grbl.origin_set)

    def test_forward_draws_in_mm_and_waits(self):
        fake = FakeGrbl()
        p = grbl_plotter(fake)
        p.forward(100)                       # 100 steps * 0.25 = 25 mm
        self.assertEqual(fake.sent, ["G4 P0", "M3 S80", "G4 P0.30",
                                     "G1 X25.000 Y0.000 F1500", "G4 P0"])

    def test_penup_travel_uses_travel_feed(self):
        fake = FakeGrbl()
        p = grbl_plotter(fake)
        p.penup()
        p.goto(0, 100)
        self.assertEqual(fake.sent, ["G1 X0.000 Y25.000 F3000", "G4 P0"])

    def test_pendown_after_penup_lowers_the_pen(self):
        fake = FakeGrbl()
        p = grbl_plotter(fake)
        p.penup()
        fake.sent.clear()
        p.pendown()
        self.assertEqual(fake.sent, ["G4 P0", "M3 S80", "G4 P0.30"])

    def test_off_paper_move_raises(self):
        fake = FakeGrbl()
        p = grbl_plotter(fake)
        p.penup()
        with self.assertRaises(PlotterError):
            p.goto(1000, 0)                  # 250 mm: off the Letter sheet

    def test_finish_lifts_returns_and_closes(self):
        fake = FakeGrbl()
        p = grbl_plotter(fake)
        p.forward(40)
        fake.sent.clear()
        p.finish()
        self.assertEqual(fake.sent, ["G4 P0", "M5", "G4 P0.30",
                                     "G1 X0.000 Y0.000 F3000", "G4 P0"])
        self.assertIsNone(p.grbl)
        self.assertTrue(fake.closed)

    def test_connect_builds_a_grbl_backend(self):
        fake = FakeGrbl()
        saved = grbl_backend._default_opener
        grbl_backend._default_opener = lambda port: fake
        try:
            turtle.Screen().tracer(0)
            p = Plotter(show_paper=False, config=CFG)
            p.connect("COM99")
            self.assertIsInstance(p.grbl, GrblBackend)
            self.assertEqual(fake.sent, ["G21", "G90"])
        finally:
            grbl_backend._default_opener = saved


if __name__ == "__main__":
    unittest.main()
