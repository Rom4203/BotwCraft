"""Offline tests of the ZIP's three installable pieces."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import zipfile

import package_botw_windows as package

class PackageTests(unittest.TestCase):
    def make_tree(self, root):
        paths = (
            "WiiXLaunch/build/switch/subsdk9",
            "botw/guest_mod/build/switch-mods/botwcraft.wxlm",
            "fabric/build/libs/skycraft-0.1.2.jar",
            "botw/host_bridge.py",
            "botw/ryujinx_log_relay.py",
            "botw/control_bridge.py",
            "botw/hud_overlay.py",
            "botw/launcher.py",
            "packaging/START_BRIDGE.bat",
            "packaging/README_INSTALL.txt",
            "THIRD-PARTY-NOTICES.md",
            "LICENSE",
        )
        for name in paths:
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"offline fake test artifact; not a real game file")

    def test_zip_has_botw_host_guest_minecraft_and_bridge(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_tree(root)
            out = package.build_zip(root / "dist" / "release.zip", root=root)
            self.assertTrue(out.is_file())
            with zipfile.ZipFile(out) as archive:
                files = archive.namelist()
                self.assertEqual(archive.testzip(), None)
                self.assertEqual(len(files), 12)
                self.assertTrue(any(p.endswith("/exefs/subsdk9") for p in files))
                self.assertTrue(any(p.endswith("/mods/botwcraft.wxlm") for p in files))
                self.assertIn("minecraft_mods/skycraft-0.1.2.jar", files)
                self.assertIn("START_BRIDGE.bat", files)
                self.assertIn("bridge/control_bridge.py", files)
                self.assertIn("bridge/hud_overlay.py", files)
                self.assertIn("bridge/launcher.py", files)
                self.assertNotIn("prod.keys", files)

    def test_missing_minecraft_mod_refuses_release(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_tree(root)
            (root / "fabric/build/libs/skycraft-0.1.2.jar").unlink()
            with self.assertRaises(FileNotFoundError):
                package.build_zip(root / "dist/release.zip", root=root)
            self.assertFalse((root / "dist/release.zip").exists())

if __name__ == "__main__":
    unittest.main()
