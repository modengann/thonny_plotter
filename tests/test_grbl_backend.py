"""
Offline tests for grbl_backend.py -- no plotter needed.

    python tests/test_grbl_backend.py
"""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

from fake_grbl import FakeGrbl, BANNER
from grbl_backend import GrblBackend, PlotStopped, usable_half
from plotter import PlotterError


def connected(fake=None, **cfg):
    fake = fake or FakeGrbl()
    b = GrblBackend(cfg, opener=lambda port: fake)
    b.connect("COM99")
    fake.sent.clear()
    fake.raw.clear()
    return b, fake


class TestPaper(unittest.TestCase):

    def test_letter_usable_area(self):
        hx, hy = usable_half()
        self.assertAlmostEqual(hx, 129.7)
        self.assertAlmostEqual(hy, 97.95)


class TestConnect(unittest.TestCase):

    def test_waits_for_banner_then_sets_units(self):
        fake = FakeGrbl()
        b = GrblBackend({}, opener=lambda port: fake)
        self.assertEqual(b.connect("COM99"), BANNER)
        self.assertEqual(fake.sent, ["G21", "G90"])
        self.assertTrue(b.connected)

    def test_no_banner_is_a_friendly_error_and_closes(self):
        fake = FakeGrbl(banner=False)
        b = GrblBackend({}, opener=lambda port: fake)
        with self.assertRaises(PlotterError) as cm:
            b.connect("COM99", banner_timeout=0.3)
        self.assertIn("didn't answer", str(cm.exception))
        self.assertFalse(b.connected)
        self.assertTrue(fake.closed)

    def test_port_in_use_mentions_candle(self):
        def opener(port):
            raise OSError("could not open port 'COM13': "
                          "PermissionError(13, 'Access is denied.')")
        b = GrblBackend({}, opener=opener)
        with self.assertRaises(PlotterError) as cm:
            b.connect("COM13")
        self.assertIn("Candle", str(cm.exception))

    def test_reconnect_clears_origin_and_pen_state(self):
        ports = [FakeGrbl(), FakeGrbl()]         # a real reopen resets the board
        b = GrblBackend({}, opener=lambda port: ports.pop(0))
        b.connect("COM99")
        b.set_origin()
        b.pen(True)
        b.connect("COM99")
        self.assertFalse(b.origin_set)
        self.assertFalse(b.is_down)

    def test_lost_connection_is_reported_and_clears_origin(self):
        b, fake = connected()
        b.set_origin()
        fake.fail_reads = True
        with self.assertRaises(PlotterError) as cm:
            b.wait()
        self.assertIn("Connection lost", str(cm.exception))
        self.assertFalse(b.connected)
        self.assertFalse(b.origin_set)


class TestPen(unittest.TestCase):

    def test_pen_down_waits_then_moves_servo_then_dwells(self):
        b, fake = connected()
        b.pen(True)
        self.assertEqual(fake.sent, ["G4 P0", "M3 S80", "G4 P0.30"])
        self.assertTrue(b.is_down)

    def test_pen_down_twice_sends_nothing_the_second_time(self):
        b, fake = connected()
        b.pen(True)
        fake.sent.clear()
        b.pen(True)
        self.assertEqual(fake.sent, [])

    def test_pen_up_is_m5(self):
        b, fake = connected()
        b.pen(True)
        fake.sent.clear()
        b.pen(False)
        self.assertEqual(fake.sent, ["G4 P0", "M5", "G4 P0.30"])

    def test_config_values_are_used(self):
        b, fake = connected(pen_down_s=95, servo_wait_s=0.5)
        b.pen(True)
        self.assertEqual(fake.sent, ["G4 P0", "M3 S95", "G4 P0.50"])

    def test_servo_to_touch_position(self):
        b, fake = connected()
        b.servo(b.pen_touch_s)
        self.assertEqual(fake.sent, ["G4 P0", "M3 S60", "G4 P0.30"])


class TestMotion(unittest.TestCase):

    def test_move_inside_paper(self):
        b, fake = connected()
        b.move(10, -5, 1500)
        self.assertEqual(fake.sent, ["G1 X10.000 Y-5.000 F1500"])

    def test_move_off_paper_raises_and_sends_nothing(self):
        b, fake = connected()
        with self.assertRaises(PlotterError) as cm:
            b.move(130.0, 0, 1500)
        self.assertIn("off the paper", str(cm.exception))
        self.assertEqual(fake.sent, [])

    def test_move_exactly_on_the_edge_is_allowed(self):
        b, fake = connected()
        b.move(129.7, -97.95, 1500)
        self.assertEqual(len(fake.sent), 1)

    def test_wait_is_g4_p0(self):
        b, fake = connected()
        b.wait()
        self.assertEqual(fake.sent, ["G4 P0"])

    def test_set_origin(self):
        b, fake = connected()
        b.set_origin()
        self.assertEqual(fake.sent, ["G4 P0", "G92 X0 Y0"])
        self.assertTrue(b.origin_set)

    def test_jog_is_relative_and_returns_to_absolute(self):
        b, fake = connected()
        b.jog(10, 0)
        self.assertEqual(fake.sent,
                         ["G91", "G1 X10.000 Y0.000 F1500", "G90", "G4 P0"])

    def test_jog_lifts_the_pen_first(self):
        b, fake = connected()
        b.pen(True)
        fake.sent.clear()
        b.jog(0, -1)
        self.assertEqual(fake.sent[:3], ["G4 P0", "M5", "G4 P0.30"])


class TestReplies(unittest.TestCase):

    def test_error_reply_names_the_command(self):
        b, fake = connected(FakeGrbl(replies={"G1": ["error:22"]}))
        with self.assertRaises(PlotterError) as cm:
            b.move(1, 1, 1500)
        self.assertIn("G1 X1.000", str(cm.exception))
        self.assertIn("error:22", str(cm.exception))

    def test_alarm_raises_and_clears_origin(self):
        b, fake = connected(FakeGrbl(replies={"G1": ["ALARM: Abort during cycle"]}))
        b.set_origin()
        with self.assertRaises(PlotterError):
            b.move(1, 1, 1500)
        self.assertFalse(b.origin_set)

    def test_read_settings(self):
        fake = FakeGrbl(replies={"$$": ["$100=80.000 (x, step/mm)",
                                        "$101=80.000 (y, step/mm)",
                                        "$22=0 (homing cycle, bool)", "ok"]})
        b, fake = connected(fake)
        self.assertEqual(b.read_settings(), {100: 80.0, 101: 80.0, 22: 0.0})

    def test_write_setting(self):
        b, fake = connected()
        b.write_setting(100, 80.53)
        self.assertEqual(fake.sent, ["$100=80.530"])


class TestStopAndPause(unittest.TestCase):

    def test_stop_sends_feed_hold_then_reset(self):
        b, fake = connected()
        b.set_origin()
        b.pen(True)
        fake.raw.clear()
        b.stop()
        self.assertEqual(fake.raw, [b"!", b"\x18"])
        self.assertFalse(b.origin_set)
        self.assertFalse(b.is_down)

    def test_command_during_stop_raises_plotstopped(self):
        b, fake = connected()
        b._stopping = True
        with self.assertRaises(PlotStopped):
            b._cmd("G1 X1 Y1 F100")

    def test_stop_while_idle_recovers(self):
        b, fake = connected()
        b.set_origin()
        b.stop()
        fake.sent.clear()
        b.recover()
        self.assertEqual(fake.sent, ["$X", "G21", "G90"])
        self.assertFalse(b.origin_set)
        b.wait()                    # usable again, no PlotStopped

    def test_pause_and_resume_are_realtime_bytes(self):
        b, fake = connected()
        b.pause()
        b.resume()
        self.assertEqual(fake.raw, [b"!", b"~"])
        self.assertEqual(fake.sent, [])

    def test_pause_extends_the_deadline(self):
        slow = {"G4 P0": [""] * 10 + ["ok"]}
        b, fake = connected(FakeGrbl(replies=slow, read_delay=0.05))
        # Pause lands after the command has gone out (mid-move).
        fake.on_line = lambda line: setattr(b, "paused", True)
        b._cmd("G4 P0", timeout=0.2)        # 0.55 s of silence: still fine
        fake.on_line = None
        b.paused = False
        with self.assertRaises(PlotterError):
            b._cmd("G4 P0", timeout=0.2)


class TestReviewFixes(unittest.TestCase):

    def test_recover_survives_a_second_stop(self):
        b, fake = connected()
        b.stop()
        seen = []

        def second_click(line):          # STOP pressed again mid-recovery
            if line == "$X" and not seen:
                seen.append(line)
                b._stopping = True
        fake.on_line = second_click
        b.recover()
        self.assertFalse(b._stopping)
        b.wait()                          # usable again

    def test_pause_holds_the_next_command_on_the_computer(self):
        import threading, time
        b, fake = connected()
        b.pause()
        t = threading.Thread(target=b.wait)
        t.start()
        time.sleep(0.3)
        self.assertNotIn("G4 P0", fake.sent)      # held while paused
        b.resume()
        t.join(5)
        self.assertIn("G4 P0", fake.sent)

    def test_stop_releases_a_command_held_by_pause(self):
        import threading, time
        b, fake = connected()
        b.pause()
        errors = []

        def run():
            try:
                b.wait()
            except PlotStopped as e:
                errors.append(e)
        t = threading.Thread(target=run)
        t.start()
        time.sleep(0.2)
        b.stop()
        t.join(5)
        self.assertEqual(len(errors), 1)


class TestHoldToJog(unittest.TestCase):

    def test_position_comes_from_the_status_report(self):
        b, fake = connected()
        b.move(12.5, -3, 1500)
        self.assertEqual(b.position(), (12.5, -3.0))

    def test_work_position_is_measured_from_the_origin(self):
        b, fake = connected()
        b.jog(20, 10)
        b.set_origin()
        b.jog(-5, 2.5)
        self.assertEqual(b.work_position(), (-5.0, 2.5))
        self.assertEqual(b.position(), (15.0, 12.5))

    def test_moves_in_short_steps_while_held(self):
        import time
        b, fake = connected()
        until = time.time() + 0.3
        b.jog_hold(1, 0, lambda: time.time() < until)
        moves = [l for l in fake.sent if l.startswith("G1")]
        self.assertGreaterEqual(len(moves), 2)
        self.assertTrue(all(l == "G1 X3.000 Y0.000 F900" for l in moves))
        self.assertEqual(fake.sent[0], "G91")
        self.assertEqual(fake.sent[-2:], ["G90", "G4 P0"])

    def test_stops_at_the_distance_cap(self):
        b, fake = connected()
        b.jog_hold(0, -1, lambda: True, max_mm=9)
        moves = [l for l in fake.sent if l.startswith("G1")]
        self.assertEqual(moves, ["G1 X0.000 Y-3.000 F900"] * 3)

    def test_lifts_the_pen_first(self):
        b, fake = connected()
        b.pen(True)
        fake.sent.clear()
        b.jog_hold(1, 0, lambda: False)
        self.assertEqual(fake.sent[:3], ["G4 P0", "M5", "G4 P0.30"])


class TestFinish(unittest.TestCase):

    def test_finish_lifts_pen_returns_to_origin_and_closes(self):
        b, fake = connected()
        b.set_origin()
        b.pen(True)
        fake.sent.clear()
        b.finish()
        self.assertEqual(fake.sent, ["G4 P0", "M5", "G4 P0.30",
                                     "G1 X0.000 Y0.000 F3000", "G4 P0"])
        self.assertTrue(fake.closed)
        self.assertFalse(b.connected)

    def test_finish_without_origin_does_not_move(self):
        b, fake = connected()
        b.finish()
        self.assertNotIn("G1 X0.000 Y0.000 F3000", fake.sent)


if __name__ == "__main__":
    unittest.main()
