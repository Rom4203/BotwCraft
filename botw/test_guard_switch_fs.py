"""Regression for the observed Ryujinx ResultFsNotMounted guest abort."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest
from botw import guard_switch_fs as fix

class SwitchFsTests(unittest.TestCase):
    def test_unmounted_sd_path_is_omitted(self):
        self.assertIn("IsSdPath(path) && !g_FSClientReady", fix.AFTER)
        self.assertIn("out[0] = nullptr;", fix.AFTER)
        self.assertIn("return;", fix.AFTER)
        self.assertIn("out[1] = out[2] = out[3] = nullptr;", fix.AFTER)

    def test_repeated_guard_does_not_duplicate_code(self):
        with TemporaryDirectory() as directory:
            file = Path(directory) / "fs.hpp"
            file.write_text("start\n" + fix.BEFORE + "\nend\n", encoding="utf-8")
            with patch.object(fix, "SOURCE", file):
                self.assertTrue(fix.guard())
                self.assertFalse(fix.guard())
            self.assertEqual(file.read_text().count("IsSdPath(path) && !g_FSClientReady"), 1)

    def test_upstream_change_refuses_unverified_patch(self):
        with TemporaryDirectory() as directory:
            file = Path(directory) / "fs.hpp"
            file.write_text("/* different upstream */", encoding="utf-8")
            with patch.object(fix, "SOURCE", file):
                with self.assertRaises(RuntimeError):
                    fix.guard()

if __name__ == "__main__":
    unittest.main()
