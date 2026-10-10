"""Verify incompatible BOTW 1.6.0 never reaches the 1.5.0 native hooks."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

from botw import guard_unknown_switch_build as version

class VersionGuardTests(unittest.TestCase):
    def test_unknown_build_skips_modloader_and_hooks(self):
        self.assertIn("GameVersion::Recognised()", version.FN_TO)
        self.assertIn("return;", version.FN_TO)
        self.assertIn("skipping native hooks and module load", version.FN_TO)

    def test_exact_patch_is_idempotent(self):
        with TemporaryDirectory() as tmp:
            p = Path(tmp)/"switch_entry.cpp"
            p.write_text(version.INCLUDE_FROM + "\n" + version.FN_FROM + "\n")
            with patch.object(version, "MAIN", p):
                self.assertTrue(version.guard())
                self.assertFalse(version.guard())
            source = p.read_text()
            self.assertIn(version.INCLUDE_TO, source)
            self.assertEqual(source.count("GameVersion::Recognised()"), 1)

    def test_unexpected_upstream_source_fails_closed(self):
        with TemporaryDirectory() as tmp:
            p = Path(tmp)/"switch_entry.cpp"
            p.write_text("void something_else() {}")
            with patch.object(version, "MAIN", p):
                with self.assertRaises(RuntimeError):
                    version.guard()

if __name__ == "__main__":
    unittest.main()
