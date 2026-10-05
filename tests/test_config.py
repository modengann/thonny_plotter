"""
Offline tests for the calibration config file.

The point of the config file is that student programs contain no numbers
that depend on this particular printer.  These tests pin down who wins when
a setting is specified in more than one place.

    python tests/test_config.py
"""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import turtle
import plotter
from plotter import Plotter, load_config, save_config


def make(**kw):
    turtle.Screen().tracer(0)
    kw.setdefault("show_paper", False)
    p = Plotter(**kw)
    p.hideturtle()
    return p


class TestPrecedence(unittest.TestCase):
    """student argument  >  config file  >  built-in default."""

    def test_defaults_when_config_is_empty(self):
        t = make(config={})
        self.assertEqual(t.pen_up_z, Plotter.DEFAULTS["pen_up_z"])
        self.assertEqual(t.paper_mm, 150.0)

    def test_config_beats_the_default(self):
        t = make(config={"pen_up_z": 12.5})
        self.assertEqual(t.pen_up_z, 12.5)

    def test_student_argument_beats_the_config(self):
        t = make(config={"pen_up_z": 12.5}, pen_up_z=3.0)
        self.assertEqual(t.pen_up_z, 3.0)

    def test_pen_offset_arrives_as_a_tuple(self):
        """JSON has no tuples, so a list must be converted or the maths breaks."""
        t = make(config={"pen_offset": [4.0, -2.0]})
        self.assertEqual(t.pen_offset, (4.0, -2.0))
        self.assertIsInstance(t.pen_offset, tuple)

    def test_offset_is_actually_applied(self):
        t = make(config={"pen_offset": [10.0, 0.0]}, bed_mm=180.0)
        nx, ny = t._nozzle(90.0, 90.0)
        self.assertAlmostEqual(nx, 80.0)
        self.assertAlmostEqual(ny, 90.0)

    def test_unknown_keys_are_ignored(self):
        make(config={"something_else": 1})       # must not raise


class TestFileHandling(unittest.TestCase):

    def test_missing_file_is_not_an_error(self):
        self.assertEqual(load_config(os.path.join(tempfile.mkdtemp(), "no.json")), {})

    def test_broken_json_is_survivable(self):
        path = os.path.join(tempfile.mkdtemp(), "bad.json")
        with open(path, "w") as f:
            f.write("{not json")
        self.assertEqual(load_config(path), {})       # warns, does not crash

    def test_a_json_list_is_rejected(self):
        path = os.path.join(tempfile.mkdtemp(), "list.json")
        with open(path, "w") as f:
            f.write("[1, 2, 3]")
        self.assertEqual(load_config(path), {})

    def test_save_then_load_round_trips(self):
        path = os.path.join(tempfile.mkdtemp(), "cfg.json")
        save_config({"pen_up_z": 7.5, "pen_offset": [1.0, 2.0]}, path)
        got = load_config(path)
        self.assertEqual(got["pen_up_z"], 7.5)
        self.assertEqual(got["pen_offset"], (1.0, 2.0))

    def test_the_real_config_file_is_valid(self):
        """Guards against a hand-edit breaking every student's program."""
        path = plotter.config_path()
        if not os.path.exists(path):
            self.skipTest("no config file yet")
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        self.assertIsInstance(data, dict)
        for key in ("pen_up_z", "pen_down_z", "pen_offset"):
            self.assertIn(key, data)
        self.assertGreater(data["pen_up_z"], data["pen_down_z"],
                           "pen up must be higher than pen down")


if __name__ == "__main__":
    unittest.main(verbosity=2, exit=False)
