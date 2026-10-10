"""Tests for fail-closed BOTW Switch C++ source patching."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from botw import guard_switch_player_hook as guard

class HookGuardTests(unittest.TestCase):
    def test_player_guard_is_idempotent_and_keeps_original(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "player.hpp"
            content = "static void Init() {\n" + guard.OLD_PLAYER + "\n}\n"
            path.write_text(content, encoding="utf-8")
            self.assertTrue(guard.guard(path, guard.OLD_PLAYER, guard.NEW_PLAYER))
            self.assertFalse(guard.guard(path, guard.OLD_PLAYER, guard.NEW_PLAYER))
            self.assertIn(guard.NEW_PLAYER, path.read_text(encoding="utf-8"))
            self.assertEqual(
                path.with_name("player.hpp.before_botwcraft_v100_guard").read_text(encoding="utf-8"),
                content,
            )

    def test_unrecognised_switch_graphics_guard(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "main.cpp"
            path.write_text(guard.OLD_NV, encoding="utf-8")
            self.assertTrue(guard.guard(path, guard.OLD_NV, guard.NEW_NV))
            self.assertIn("GameVersion::Recognised()", path.read_text(encoding="utf-8"))

    def test_unknown_upstream_version_is_not_modified(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "player.hpp"
            path.write_text("This SDK has completely different symbols\n", encoding="utf-8")
            with self.assertRaises(RuntimeError):
                guard.guard(path, guard.OLD_PLAYER, guard.NEW_PLAYER)
            self.assertEqual(path.read_text(encoding="utf-8"),
                             "This SDK has completely different symbols\n")
            self.assertFalse(path.with_name("player.hpp.before_botwcraft_v100_guard").exists())

if __name__ == "__main__":
    unittest.main()
