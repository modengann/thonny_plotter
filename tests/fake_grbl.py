"""
fake_grbl.py  -  a stand-in for the AX4's serial port, for offline tests.

Behaves like GRBL 0.9i as measured on 2026-10-04:
  * a banner when "opened" and again after a Ctrl-X soft reset
  * "ok" for every line, unless `replies` says otherwise
  * realtime bytes (!, ~, ?) get no "ok"
"""

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
        self._pending = ["", BANNER] if banner else []

    def write(self, data):
        self.raw.append(bytes(data))
        if data in (b"!", b"~"):
            return len(data)
        if data == b"?":
            self._pending.append(
                "<Idle,MPos:0.000,0.000,0.000,WPos:0.000,0.000,0.000>")
            return 1
        if data == b"\x18":
            self._pending += ["", BANNER]
            return 1
        line = data.decode("ascii").strip()
        self.sent.append(line)
        if self.on_line:
            self.on_line(line)
        for prefix, lines in self.replies.items():
            if line.startswith(prefix):
                self._pending += list(lines)
                break
        else:
            self._pending.append("ok")
        return len(data)

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
