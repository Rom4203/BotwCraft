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
            "botw/native_mesh_bridge.py",
            "botw/hud_overlay.py",
            "botw/launcher.py",
            "botw/prism_discovery.py",
            "packaging/START_BRIDGE.bat",
            "packaging/INSTALL_NATIVE_TEST.bat",
            "botw/install_native.py",
            "botw/install_native_mc.py",
            "botw/install_preview.py",
            "botw/prism_discovery.py",
            "tools/minecraft-bundle/Prism/instances/SkyCraft/instance.cfg",
            "tools/minecraft-bundle/Prism/instances/SkyCraft/mmc-pack.json",
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
                self.assertEqual(len(files), 21)
                self.assertTrue(any(p.endswith("/exefs/subsdk9") for p in files))
                self.assertIn("ryujinx_sdcard/WiiXLaunch/mods/01007EF00011E000/botwcraft.wxlm", files)
                self.assertIn("minecraft_mods/skycraft-0.1.2.jar", files)
                self.assertIn("START_BRIDGE.bat", files)
                self.assertIn("INSTALL_NATIVE_TEST.bat", files)
                self.assertIn("install_native.py", files)
                self.assertIn("install_native_mc.py", files)
                self.assertIn("prism_template/mmc-pack.json", files)
                self.assertFalse(any("/romfs/WiiXLaunch/" in p for p in files))
                self.assertIn("bridge/control_bridge.py", files)
                self.assertIn("bridge/native_mesh_bridge.py", files)
                self.assertIn("bridge/hud_overlay.py", files)
                self.assertIn("bridge/launcher.py", files)
                self.assertIn("bridge/prism_discovery.py", files)
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
