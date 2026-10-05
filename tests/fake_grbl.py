"""
fake_grbl.py  -  a stand-in for the AX4's serial port, for offline tests.

Behaves like GRBL 0.9i as measured on 2026-10-04:
  * a banner when "opened" and again after a Ctrl-X soft reset
  * "ok" for every line, unless `replies` says otherwise
  * realtime bytes (!, ~, ?) get no "ok"
"""

import re
import time

BANNER = "Grbl 0.9i ['$' for help]"


class FakeGrbl:

    def __init__(self, replies=None, banner=True, read_delay=0.0):
        self.replies = dict(replies or {})  # command prefix -> reply lines
        self.sent = []          # text lines received, newline stripped
        self.raw = []           # every write, as bytes
        self.read_delay = read_delay
        self.fail_reads = False
        self.closed = False
        self.on_line = None     # test hook: called with each text line
        self.pos = [0.0, 0.0]   # machine position; moves finish instantly
        self.relative = False
        self._pending = ["", BANNER] if banner else []

    def write(self, data):
        self.raw.append(bytes(data))
        if data in (b"!", b"~"):
            return len(data)
        if data == b"?":
            self._pending.append(
                "<Idle,MPos:%.3f,%.3f,0.000,WPos:%.3f,%.3f,0.000>"
                % (self.pos[0], self.pos[1], self.pos[0], self.pos[1]))
            return 1
        if data == b"\x18":
            self._pending += ["", BANNER]
            return 1
        line = data.decode("ascii").strip()
        self.sent.append(line)
        if self.on_line:
            self.on_line(line)
        self._track(line)
        for prefix, lines in self.replies.items():
            if line.startswith(prefix):
                self._pending += list(lines)
                break
        else:
            self._pending.append("ok")
        return len(data)

    def _track(self, line):
        if line == "G91":
            self.relative = True
        elif line == "G90":
            self.relative = False
        elif line.startswith("G1 "):
            for i, axis in enumerate("XY"):
                m = re.search(axis + r"(-?[\d.]+)", line)
                if m:
                    v = float(m.group(1))
                    self.pos[i] = self.pos[i] + v if self.relative else v

    def readline(self):
        if self.fail_reads:
            raise OSError("device disconnected")
        if self.read_delay:
            time.sleep(self.read_delay)
        if not self._pending:
            return b""              # looks like a read timeout
        return (self._pending.pop(0) + "\r\n").encode("ascii")

    def close(self):
        self.closed = True
