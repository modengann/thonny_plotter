"""
Tests for upload_server.py using Flask's test client - no network.

    python tests/test_upload_server.py
"""

import datetime
import io
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import upload_server as us

GOOD = b"import turtle\nturtle.forward(50)\n"


class TestCleanName(unittest.TestCase):

    def test_spaces_and_symbols(self):
        self.assertEqual(us.clean_name("  Ana Lee!/.. "), "Ana_Lee")

    def test_hangeul_kept(self):
        self.assertEqual(us.clean_name("김민수"), "김민수")

    def test_empty_or_only_symbols(self):
        self.assertEqual(us.clean_name(""), "student")
        self.assertEqual(us.clean_name("../"), "student")

    def test_long_names_are_cut(self):
        self.assertEqual(len(us.clean_name("a" * 50)), 30)


class TempFolder(unittest.TestCase):

    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.dir)


class TestSave(TempFolder):

    def test_same_second_does_not_overwrite(self):
        now = datetime.datetime(2026, 10, 8, 9, 30, 0)
        a = us.save_upload(self.dir, "ana", "x = 1\n", now)
        b = us.save_upload(self.dir, "ana", "x = 2\n", now)
        self.assertEqual(a, "ana_20261008-093000.py")
        self.assertEqual(b, "ana_20261008-093000_2.py")
        with open(os.path.join(self.dir, a), encoding="utf-8") as f:
            self.assertEqual(f.read(), "x = 1\n")

    def test_recent_is_newest_first(self):
        old = us.save_upload(self.dir, "old", "x = 1\n")
        new = us.save_upload(self.dir, "new", "x = 1\n")
        os.utime(os.path.join(self.dir, old), (1000, 1000))
        os.utime(os.path.join(self.dir, new), (2000, 2000))
        self.assertEqual(us.recent(self.dir), [new, old])


class TestPage(TempFolder):

    def setUp(self):
        super().setUp()
        app = us.create_app(self.dir)
        app.testing = True
        self.client = app.test_client()

    def post(self, name, filename, data):
        return self.client.post(
            "/", data={"name": name, "file": (io.BytesIO(data), filename)},
            content_type="multipart/form-data")

    def saved(self):
        return os.listdir(self.dir)

    def test_page_links_to_the_dashboard_on_the_same_host(self):
        r = self.client.get("/", base_url="http://10.0.0.5:8000")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"http://10.0.0.5:6080/vnc.html", r.data)

    def test_good_upload_is_saved(self):
        r = self.post("Ana", "spiral.py", GOOD)
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"Uploaded", r.data)
        files = self.saved()
        self.assertEqual(len(files), 1)
        self.assertTrue(files[0].startswith("Ana_"))
        self.assertIn(files[0].encode(), r.data)      # shows in the list
        with open(os.path.join(self.dir, files[0]), "rb") as f:
            self.assertEqual(f.read(), GOOD)

    def test_bad_code_is_refused_with_the_reason(self):
        r = self.post("Ana", "x.py", b"import os\n")
        self.assertEqual(self.saved(), [])
        self.assertIn(b"Line 1: ", r.data)
        self.assertIn(b"(not os)", r.data)

    def test_bom_file_is_accepted(self):
        self.post("Ana", "x.py", b"\xef\xbb\xbf" + GOOD)
        files = self.saved()
        self.assertEqual(len(files), 1)
        with open(os.path.join(self.dir, files[0]), "rb") as f:
            self.assertEqual(f.read(), GOOD)

    def test_only_py_files(self):
        r = self.post("Ana", "picture.png", GOOD)
        self.assertEqual(self.saved(), [])
        self.assertIn(b".py", r.data)

    def test_not_utf8_is_refused(self):
        r = self.post("Ana", "x.py", b"x = '\xff\xfe'\n")
        self.assertEqual(self.saved(), [])
        self.assertIn(b"UTF-8", r.data)

    def test_no_file_chosen(self):
        r = self.client.post("/", data={"name": "Ana"},
                             content_type="multipart/form-data")
        self.assertEqual(self.saved(), [])
        self.assertIn(b"Choose a file", r.data)

    def test_too_big_has_a_friendly_message(self):
        for size in (us.MAX_BYTES + 1, us.MAX_BYTES * 3):
            r = self.post("Ana", "x.py", b"#" * size)
            self.assertIn(b"too big", r.data, size)
        self.assertEqual(self.saved(), [])


if __name__ == "__main__":
    unittest.main()
