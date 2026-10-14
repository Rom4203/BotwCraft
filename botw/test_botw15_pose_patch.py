"""Test exact BOTW Switch 1.5.0 Link pose patch, no Nintendo data required."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

from botw import patch_botw15_player_pose as game

SOURCE = (
    "#include <wiixlaunch/game_version.hpp>\n"
    "void WiiXLaunch_Init() {\n"
    "#if WIIXL_SWITCH\n"
    "    if (WiiXLaunch::GameVersion::Recognised()) {\n"
    "        NVN::Init();\n"
    "    }\n"
    "#endif\n"
    "}\n"
)

class SwitchPosePatchTests(unittest.TestCase):
    def test_documented_15_symbols_and_exact_version_guard(self):
        self.assertIn("0x25CDB60", game.HEADER_CONTENT)
        self.assertIn("0x854BA0", game.HEADER_CONTENT)
        self.assertIn("0x854BA8", game.HEADER_CONTENT)
        self.assertIn("0xA982D2BC", game.HEADER_CONTENT)
        self.assertIn("GameVersion::Fingerprint() != kExpectedFingerprint",
                      game.HEADER_CONTENT)
        self.assertNotIn("0x873374", game.HEADER_CONTENT)  # crashed on 1.0.0
        self.assertIn("getPlayer", game.HEADER_CONTENT)
        self.assertIn("getPos(info)", game.HEADER_CONTENT)

    def test_requires_guarded_host_and_is_idempotent(self):
        with TemporaryDirectory() as temp:
            folder = Path(temp)
            main = folder / "main.cpp"
            header = folder / "botwcraft_switch15_pose.hpp"
            main.write_text(SOURCE)
            with patch.object(game, "MAIN", main), patch.object(game, "HEADER", header):
                self.assertTrue(game.patch())
                self.assertIn("BotwCraft15::Register();", main.read_text())
                self.assertIn("botwcraft_switch15_pose.hpp", main.read_text())
                self.assertEqual(header.read_text(), game.HEADER_CONTENT)
                self.assertFalse(game.patch())
                self.assertEqual(main.read_text().count("BotwCraft15::Register();"), 1)

    def test_refuses_unrecognised_upstream_code(self):
        with TemporaryDirectory() as temp:
            folder = Path(temp)
            main = folder / "main.cpp"
            header = folder / "botwcraft_switch15_pose.hpp"
            main.write_text("int main() { return 0; }")
            with patch.object(game, "MAIN", main), patch.object(game, "HEADER", header):
                with self.assertRaises(RuntimeError):
                    game.patch()
                self.assertFalse(header.exists())

    def test_rejects_modified_existing_native_header(self):
        with TemporaryDirectory() as temp:
            folder = Path(temp)
            main = folder / "main.cpp"
            header = folder / "botwcraft_switch15_pose.hpp"
            main.write_text(SOURCE)
            header.write_text("conflicting user file")
            with patch.object(game, "MAIN", main), patch.object(game, "HEADER", header):
                with self.assertRaises(RuntimeError):
                    game.patch()
                self.assertEqual(main.read_text(), SOURCE)

if __name__ == "__main__":
    unittest.main()
