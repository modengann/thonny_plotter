"""
Offline tests for the serial protocol -- no printer needed.

A FakeSerial stands in for the real port and replies the way Buddy firmware
does: a boot banner, echo lines, "busy: processing" while it works,
temperature reports, and finally "ok".

Run from the project root:

    python tests/test_serial_protocol.py
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import plotter
from plotter import (Plotter, PlotterError, _is_chatter,
                     _friendly_open_error, _looks_like_bluetooth)


class FakeSerial:
    """Replays a scripted list of reply lines, one per readline() call.

    `replies` is a list of lists: one list of lines per command sent.
    """

    def __init__(self, replies):
        self.replies = list(replies)
        self.sent = []
        self._pending = []

    def write(self, data):
        self.sent.append(data.decode("ascii").strip())
        if self.replies:
            self._pending = list(self.replies.pop(0))
        else:
            self._pending = ["ok"]
        return len(data)

    def flush(self):
        pass

    def readline(self):
        if not self._pending:
            return b""              # looks like a read timeout
        return (self._pending.pop(0) + "\n").encode("ascii")

    def reset_input_buffer(self):
        self._pending = []

    def close(self):
        pass


def bare_plotter():
    """A Plotter that never touches the screen or a real port."""
    p = Plotter.__new__(Plotter)        # skip turtle.__init__ entirely
    p.ser = None
    p._hw_down = False
    p._homed = False
    p.firmware = None
    p.pen_up_z = 5.0
    p.pen_down_z = 1.0
    return p


class TestChatterFilter(unittest.TestCase):

    def test_known_noise_is_recognised(self):
        for line in ["echo:busy", "// action:notification", "start", "wait"]:
            self.assertTrue(_is_chatter(line), line)

    def test_temperature_reports_are_dropped_unless_collecting(self):
        self.assertTrue(_is_chatter("T:24.1 /0.0 B:23.8 /0.0"))
        self.assertFalse(_is_chatter("T:24.1 /0.0 B:23.8 /0.0", collecting=True))

    def test_replies_to_our_own_questions_survive(self):
        """The bug: these were filtered, so M115 and M114 looked silent."""
        for line in ["FIRMWARE_NAME:Prusa-Firmware-Buddy FIRMWARE_VERSION:4.7.2",
                     "Cap:EEPROM:1",
                     "X:0.00 Y:0.00 Z:0.00 E:0.00 Count: A:0 B:0 C:0"]:
            self.assertFalse(_is_chatter(line, collecting=True), line)

    def test_real_content_is_not_chatter(self):
        for line in ["ok", "Error:foo", "SD card released"]:
            self.assertFalse(_is_chatter(line), line)


class TestSend(unittest.TestCase):

    def test_ok_ends_the_command(self):
        p = bare_plotter()
        p.ser = FakeSerial([["ok"]])
        p._send("G21")
        self.assertEqual(p.ser.sent, ["G21"])

    def test_chatter_before_ok_is_skipped(self):
        p = bare_plotter()
        p.ser = FakeSerial([["echo:enqueueing", "T:24.1 /0.0", "wait", "ok"]])
        p._send("G21")          # must not raise

    def test_busy_does_not_count_as_a_stall(self):
        p = bare_plotter()
        p.ser = FakeSerial([["busy: processing"] * 50 + ["ok"]])
        p._send("G28", timeout=5)

    def test_ok_with_trailing_temperature_still_counts(self):
        p = bare_plotter()
        p.ser = FakeSerial([["ok T:24.1 /0.0"]])
        p._send("M105")

    def test_error_raises_a_readable_message(self):
        p = bare_plotter()
        p.ser = FakeSerial([["Error:Printer halted"]])
        with self.assertRaises(PlotterError) as cm:
            p._send("G1 X10")
        self.assertIn("Printer halted", str(cm.exception))
        self.assertIn("G1 X10", str(cm.exception))

    def test_silence_times_out_with_advice(self):
        p = bare_plotter()
        p.ser = FakeSerial([[]])        # no reply at all
        with self.assertRaises(PlotterError) as cm:
            p._send("M115", timeout=1)
        self.assertIn("stopped replying", str(cm.exception))

    def test_collect_returns_the_firmware_lines(self):
        p = bare_plotter()
        p.ser = FakeSerial([[
            "echo:unwanted noise",
            "FIRMWARE_NAME:Prusa-Firmware-Buddy FIRMWARE_VERSION:4.7.2",
            "Cap:EEPROM:1",
            "SD card ok",
            "ok",
        ]])
        got = p._send("M115", collect=True)
        # the firmware's own answer must survive the chatter filter
        self.assertTrue(any("FIRMWARE_NAME" in g for g in got), got)
        self.assertIn("Cap:EEPROM:1", got)
        self.assertIn("SD card ok", got)

    def test_send_without_a_connection_is_a_friendly_error(self):
        p = bare_plotter()
        with self.assertRaises(PlotterError):
            p._send("G21")


class TestFriendlyErrors(unittest.TestCase):

    def test_port_busy_mentions_one_at_a_time(self):
        msg = _friendly_open_error("COM3", Exception(
            "could not open port COM3: PermissionError(13, 'Access is denied.')"))
        self.assertIn("already in use", msg)
        self.assertIn("one person", msg)

    def test_unknown_error_still_names_the_port(self):
        msg = _friendly_open_error("COM9", Exception("something odd"))
        self.assertIn("COM9", msg)

    def test_no_pyserial_gives_thonny_instructions(self):
        p = bare_plotter()
        saved = plotter.serial
        plotter.serial = None
        try:
            with self.assertRaises(PlotterError) as cm:
                p.connect()
            self.assertIn("Manage packages", str(cm.exception))
        finally:
            plotter.serial = saved

    def test_no_printer_found_suggests_the_cable(self):
        p = bare_plotter()
        saved = plotter.find_prusa_port
        plotter.find_prusa_port = lambda: None
        try:
            with self.assertRaises(PlotterError) as cm:
                p.connect()
            self.assertIn("cable", str(cm.exception))
        finally:
            plotter.find_prusa_port = saved


class TestConnectMovesNothing(unittest.TestCase):

    def test_connect_sends_no_motion_commands(self):
        p = bare_plotter()
        p.ser = FakeSerial([])          # every command answers plain "ok"
        # bypass port discovery: pretend the port is already open
        p.firmware = None
        sent = []

        def fake_send(line, timeout=30, collect=False):
            sent.append(line)
            return ["FIRMWARE_NAME:Prusa-Firmware-Buddy"] if collect else []

        p._send = fake_send
        # run just the handshake half of connect()
        p.firmware = " | ".join(fake_send("M115", collect=True))
        for cmd in ["M155 S0", "M104 S0", "M140 S0", "M107", "G21", "G90"]:
            fake_send(cmd)

        for line in sent:
            self.assertFalse(line.startswith("G28"), "connect must not home")
            self.assertFalse(line.startswith("G1"), "connect must not move")

    def test_prepare_refuses_without_a_connection(self):
        p = bare_plotter()
        with self.assertRaises(PlotterError):
            p.prepare()


class TestPortGuessing(unittest.TestCase):
    """A wrong guess means talking to somebody's Bluetooth headset."""

    def test_bluetooth_ports_are_rejected(self):
        self.assertTrue(_looks_like_bluetooth(
            "COM5", "Standard Serial over Bluetooth link (COM5)"))

    def test_a_real_usb_port_is_not_rejected(self):
        self.assertFalse(_looks_like_bluetooth("COM4", "USB Serial Device"))
        self.assertFalse(_looks_like_bluetooth("/dev/cu.usbmodem14201", ""))

    def test_prusa_vid_wins(self):
        saved = plotter.find_ports
        plotter.find_ports = lambda: [
            ("COM5", "Standard Serial over Bluetooth link", None),
            ("COM4", "USB Serial Device", plotter.PRUSA_VID),
        ]
        try:
            self.assertEqual(plotter.find_prusa_port(), "COM4")
        finally:
            plotter.find_ports = saved

    def test_only_bluetooth_means_no_printer(self):
        saved = plotter.find_ports
        plotter.find_ports = lambda: [
            ("COM5", "Standard Serial over Bluetooth link", None),
            ("COM3", "Standard Serial over Bluetooth link", None),
        ]
        try:
            self.assertIsNone(plotter.find_prusa_port())
        finally:
            plotter.find_ports = saved

    def test_usbmodem_is_accepted_on_mac(self):
        saved = plotter.find_ports
        plotter.find_ports = lambda: [("/dev/cu.usbmodem14201", "Prusa MINI", None)]
        try:
            self.assertEqual(plotter.find_prusa_port(), "/dev/cu.usbmodem14201")
        finally:
            plotter.find_ports = saved


if __name__ == "__main__":
    unittest.main(verbosity=2, exit=False)
