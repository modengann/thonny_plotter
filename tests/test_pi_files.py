"""
Checks on the Raspberry Pi setup files that can be made on Windows:
line endings (bash and systemd choke on CR), shebangs, bash syntax, and
that every service file is filled in by setup.sh.

    python tests/test_pi_files.py
"""

import glob
import os
import shutil
import subprocess
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PI = os.path.join(ROOT, "pi")
SCRIPTS = ("setup.sh", "start-display.sh")
SERVICES = ("plotter-display.service", "plotter-vnc.service",
            "plotter-novnc.service", "plotter-upload.service")


def read(name):
    with open(os.path.join(PI, name), "rb") as f:
        return f.read()


class TestPiFiles(unittest.TestCase):

    def test_all_files_exist(self):
        for name in SCRIPTS + SERVICES:
            self.assertTrue(os.path.isfile(os.path.join(PI, name)), name)

    def test_no_windows_line_endings(self):
        for path in glob.glob(os.path.join(PI, "*")):
            with open(path, "rb") as f:
                self.assertNotIn(b"\r", f.read(), path)

    def test_scripts_are_bash(self):
        for name in SCRIPTS:
            self.assertTrue(read(name).startswith(b"#!/bin/bash\n"), name)

    @unittest.skipUnless(shutil.which("bash"), "no bash here")
    def test_scripts_parse(self):
        for name in SCRIPTS:
            out = subprocess.run(["bash", "-n", os.path.join(PI, name)],
                                 capture_output=True, text=True)
            self.assertEqual(out.returncode, 0, name + ": " + out.stderr)

    def test_services_use_the_placeholders_setup_fills(self):
        for name in SERVICES:
            text = read(name).decode()
            self.assertIn("User=@USER@", text, name)
            self.assertIn("[Install]", text, name)
            self.assertIn("Restart=always", text, name)

    def test_setup_installs_fonts_for_korean_names(self):
        text = read("setup.sh").decode()
        self.assertIn("fonts-nanum", text)
        self.assertIn("xfonts-base", text)

    def test_setup_installs_every_service(self):
        text = read("setup.sh").decode()
        for name in SERVICES:
            self.assertIn(name.replace(".service", ""), text, name)


if __name__ == "__main__":
    unittest.main()
