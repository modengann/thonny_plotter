"""
Tests for stop_button.py with a pretend button - no GPIO needed.

    python tests/test_stop_button.py
"""

import os
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import stop_button


class FakeButton:
    def __init__(self, pin, pull_up, bounce_time):
        self.pin = pin
        self.pull_up = pull_up
        self.when_pressed = None


class NoGpio:
    def __init__(self, *args, **kwargs):
        raise RuntimeError("no GPIO on this machine")


class TestAttach(unittest.TestCase):

    def test_no_pin_means_no_button(self):
        self.assertIsNone(stop_button.attach(None, print, FakeButton))

    def test_pressing_the_button_calls_back(self):
        presses = []
        b = stop_button.attach(17, lambda: presses.append(1), FakeButton)
        self.assertEqual(b.pin, 17)
        self.assertTrue(b.pull_up)
        b.when_pressed()
        self.assertEqual(presses, [1])

    def test_no_gpio_hardware_is_ignored(self):
        self.assertIsNone(stop_button.attach(17, print, NoGpio))

    def test_gpiozero_missing_is_ignored(self):
        with mock.patch.dict(sys.modules, {"gpiozero": None}):
            self.assertIsNone(stop_button.attach(17, print))


if __name__ == "__main__":
    unittest.main()
