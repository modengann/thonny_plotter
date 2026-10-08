"""
Tests for run_turtle.py: runs sample student programs in a subprocess,
exactly as the dashboard does.

    python tests/test_run_turtle.py
"""

import json
import os
import subprocess
import sys
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
RUNNER = os.path.join(ROOT, "run_turtle.py")
SAMPLES = os.path.join(HERE, "samples")

sys.path.insert(0, ROOT)
import run_turtle


def run_sample(name):
    out = subprocess.run([sys.executable, RUNNER, os.path.join(SAMPLES, name)],
                         capture_output=True, text=True, encoding="utf-8",
                         timeout=60)
    return json.loads(out.stdout)


class TestRunner(unittest.TestCase):

    def test_object_style_square(self):
        r = run_sample("square.py")
        self.assertIsNone(r["error"])
        self.assertEqual(len(r["strokes"]), 1)
        s = r["strokes"][0]
        self.assertEqual(len(s), 5)
        self.assertEqual(s[0], [0, 0])
        self.assertEqual(s[1], [100, 0])
        self.assertAlmostEqual(s[2][1], 100, places=3)

    def test_module_level_functions_record(self):
        r = run_sample("module_level.py")
        self.assertIsNone(r["error"])
        self.assertEqual(r["strokes"], [[[0, 0], [50, 0]],
                                        [[0, 100], [20, 100]]])

    def test_two_turtles_keep_code_order(self):
        r = run_sample("two_turtles.py")
        s = r["strokes"]
        self.assertEqual(len(s), 3)
        self.assertEqual(s[0], [[0, 0], [10, 0]])
        self.assertAlmostEqual(s[1][1][1], 10, places=3)     # b went up
        self.assertEqual(s[2], [[10, 0], [20, 0]])

    def test_runtime_error_keeps_partial_drawing(self):
        r = run_sample("typo.py")
        self.assertEqual(r["error"]["type"], "AttributeError")
        self.assertEqual(r["error"]["line"], 5)
        self.assertEqual(r["strokes"], [[[0, 0], [50, 0]]])

    def test_syntax_error_has_a_line(self):
        r = run_sample("syntax_error.py")
        self.assertEqual(r["error"]["type"], "SyntaxError")
        self.assertIn(r["error"]["line"], (2, 3))
        self.assertEqual(r["strokes"], [])

    def test_input_is_refused_clearly(self):
        r = run_sample("asks_input.py")
        self.assertEqual(r["error"]["type"], "KeyboardInputNotSupported")
        self.assertIn("keyboard input", r["error"]["message"])

    def test_fill_write_and_colours_warn(self):
        r = run_sample("fill_write_colour.py")
        self.assertIsNone(r["error"])
        self.assertIn(run_turtle.W_FILL, r["warnings"])
        self.assertIn(run_turtle.W_WRITE, r["warnings"])
        self.assertIn(run_turtle.W_COLOUR, r["warnings"])
        self.assertEqual(len(r["strokes"]), 2)

    def test_student_print_does_not_corrupt_json(self):
        r = run_sample("prints.py")
        self.assertIsNone(r["error"])
        self.assertEqual(r["strokes"], [[[0, 0], [10, 0]]])

    def test_program_that_draws_nothing(self):
        r = run_sample("nothing.py")
        self.assertIsNone(r["error"])
        self.assertEqual(r["strokes"], [])


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


if __name__ == "__main__":
    unittest.main()
