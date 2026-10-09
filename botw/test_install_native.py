"""Tests that installation uses Ryujinx virtual SD, not a RomFS dead path.

Everything below is synthetic local test data; no game files or personal
Ryujinx profile are read or modified by tests.
"""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from botw import install_native


class NativeInstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.bundle = root / "bundle"
        self.ryujinx = root / "ryujinx"
        self.oldbackup = root / "backups"
        exe = (self.bundle / "ryujinx_mods" / "contents" / install_native.TITLE_ID /
               "BotwCraft" / "exefs" / "subsdk9")
        guest = (self.bundle / "ryujinx_sdcard" / "WiiXLaunch" / "mods" /
                 install_native.TITLE_ID_UPPER / "botwcraft.wxlm")
        for path in (exe, guest):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(bytes(range(256)))
        (self.ryujinx / "mods" / "contents").mkdir(parents=True)
        (self.ryujinx / "sdcard").mkdir()

    def test_installs_real_locations_and_never_romfs(self):
        exe, guest = install_native.install(self.bundle, self.ryujinx,
                                           backup_root=self.oldbackup)
        self.assertTrue(exe.is_file())
        self.assertTrue(guest.is_file())
        self.assertIn("mods/contents", exe.as_posix())
        self.assertIn("sdcard/WiiXLaunch/mods", guest.as_posix())
        self.assertNotIn("/romfs/", exe.as_posix())
        self.assertNotIn("/romfs/", guest.as_posix())

    def test_existing_mods_backup_outside_active_mod_directory(self):
        installed_exe, installed_guest = install_native.install(
            self.bundle, self.ryujinx, backup_root=self.oldbackup)
        installed_exe.write_bytes(b"old host data")
        installed_guest.write_bytes(b"old guest data")
        install_native.install(self.bundle, self.ryujinx,
                               backup_root=self.oldbackup)
        self.assertEqual(installed_exe.read_bytes(), bytes(range(256)))
        saved = list(self.oldbackup.glob("*/old_BotwCraft_mod/exefs/subsdk9"))
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0].read_bytes(), b"old host data")
        saved_guest = list(self.oldbackup.glob("*/old_botwcraft.wxlm"))
        self.assertEqual(len(saved_guest), 1)
        self.assertEqual(saved_guest[0].read_bytes(), b"old guest data")

    def test_never_creates_fake_ryujinx_profile(self):
        fake = self.ryujinx.parent / "not_ryujinx"
        with self.assertRaises(ValueError):
            install_native.install(self.bundle, fake, backup_root=self.oldbackup)
        self.assertFalse(fake.exists())

    def test_rejects_missing_binary_without_modification(self):
        bad = self.bundle / "ryujinx_sdcard" / "WiiXLaunch" / "mods"
        guest = bad / install_native.TITLE_ID_UPPER / "botwcraft.wxlm"
        guest.unlink()
        with self.assertRaises(FileNotFoundError):
            install_native.install(self.bundle, self.ryujinx,
                                   backup_root=self.oldbackup)
        self.assertFalse((self.ryujinx / "mods/contents" /
                          install_native.TITLE_ID / "BotwCraft").exists())

if __name__ == "__main__":
    unittest.main()
