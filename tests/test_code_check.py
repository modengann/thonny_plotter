"""
Tests for code_check.py -- the static check run on every student program
before it is saved or run.  No subprocess, nothing is executed.

    python tests/test_code_check.py
"""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from code_check import check

SAMPLES = os.path.join(HERE, "samples")


class TestAccepted(unittest.TestCase):

    def test_every_sample_but_the_syntax_error_passes(self):
        for name in sorted(os.listdir(SAMPLES)):
            if not name.endswith(".py") or name == "syntax_error.py":
                continue
            with open(os.path.join(SAMPLES, name), encoding="utf-8") as f:
                self.assertEqual(check(f.read()), [], name)

    def test_allowed_modules(self):
        src = ("import turtle\nimport math, random\nfrom time import sleep\n"
               "import colorsys as c\nfrom turtle import *\nimport turtle as t\n")
        self.assertEqual(check(src), [])

    def test_main_guard_is_allowed(self):
        src = ("import turtle\n\ndef main():\n    turtle.forward(10)\n\n"
               "if __name__ == '__main__':\n    main()\n")
        self.assertEqual(check(src), [])

    def test_input_and_private_looking_variables_are_allowed(self):
        src = "n = int(input('How many? '))\n_size = 5\n"
        self.assertEqual(check(src), [])


class TestRejected(unittest.TestCase):

    def assertRejected(self, src, line, word):
        problems = check(src)
        self.assertTrue(problems, src)
        self.assertTrue(problems[0].startswith("Line %d: " % line), problems)
        self.assertIn(word, problems[0])

    def test_other_imports(self):
        self.assertRejected("import os\n", 1, "os")
        self.assertRejected("import turtle\nfrom subprocess import run\n", 2,
                            "subprocess")
        self.assertRejected("import os.path\n", 1, "os")
        self.assertRejected("from . import thing\n", 1, "import")

    def test_import_message_lists_what_is_allowed(self):
        self.assertIn("turtle, math, random, time, colorsys", check("import os\n")[0])

    def test_dangerous_builtins(self):
        self.assertRejected("f = open('x.txt')\n", 1, "open")
        self.assertRejected("eval('1+1')\n", 1, "eval")
        self.assertRejected("x = 1\nexec('x = 2')\n", 2, "exec")
        self.assertRejected("__import__('os')\n", 1, "__import__")
        self.assertRejected("g = getattr\n", 1, "getattr")

    def test_dunder_escapes(self):
        self.assertRejected("x = ().__class__\n", 1, "__class__")
        self.assertRejected("__builtins__['eval']\n", 1, "__builtins__")

    def test_private_turtle_internals(self):
        self.assertRejected("import turtle\nt = turtle.Turtle()\nt._tracer(0)\n",
                            3, "_tracer")

    def test_routes_to_tk(self):
        self.assertRejected("import turtle\nturtle.getscreen().getcanvas()\n",
                            2, "getcanvas")
        self.assertRejected("from turtle import *\ngetcanvas()\n", 2, "getcanvas")
        self.assertRejected("from turtle import getcanvas\n", 1, "getcanvas")
        self.assertRejected("import turtle\nturtle.TK.Tk()\n", 2, "TK")

    def test_syntax_error_has_a_line(self):
        src = "import turtle\nfor i in range(3)\n    turtle.forward(10)\n"
        self.assertRejected(src, 2, "can't read")

    def test_one_problem_per_line_in_order(self):
        problems = check("import sys\nimport os\n")
        self.assertEqual(len(problems), 2)
        self.assertTrue(problems[0].startswith("Line 1: "))
        self.assertTrue(problems[1].startswith("Line 2: "))


if __name__ == "__main__":
    unittest.main()
