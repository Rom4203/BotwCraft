"""No-GUI tests for portable and installed Prism resolution on Windows."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from botw import prism_discovery as locator

class PrismTests(unittest.TestCase):
    def test_saved_executable_is_preferred_over_other_paths(self):
        with TemporaryDirectory() as d:
            root = Path(d)
            portable = root / "PrismLauncher"
            portable.mkdir()
            exe = portable / "prismlauncher.exe"
            exe.write_bytes(b"stub for path tests")
            saved = root / "prism-location.txt"
            saved.write_text(str(exe), encoding="utf-8")
            found = locator.locate_prism(
                allow_picker=False, module_file=str(root / "prism_discovery.py"),
                env={"LOCALAPPDATA": str(root / "none")})
            self.assertEqual(found, exe.resolve())

    def test_portable_root_with_flag(self):
        with TemporaryDirectory() as d:
            root = Path(d)
            exe = root / "prismlauncher.exe"
            exe.write_bytes(b"binary mock")
            (root / "portable.txt").touch()
            self.assertEqual(locator.prism_data_dir(exe, env={}), root.resolve())

    def test_portable_userdata_has_precedence(self):
        with TemporaryDirectory() as d:
            root = Path(d)
            exe = root / "prismlauncher.exe"
            exe.write_bytes(b"binary mock")
            (root / "portable.txt").touch()
            (root / "UserData").mkdir()
            self.assertEqual(locator.prism_data_dir(exe, env={}),
                             (root / "UserData").resolve())

    def test_standard_appdata_profile(self):
        with TemporaryDirectory() as d:
            root = Path(d)
            exe = root / "prismlauncher.exe"
            exe.write_bytes(b"binary mock")
            self.assertEqual(locator.prism_data_dir(exe, env={"APPDATA": d}),
                             root / "PrismLauncher")

    def test_env_prism_path(self):
        with TemporaryDirectory() as d:
            root = Path(d)
            exe = root / "prismlauncher.exe"
            exe.write_bytes(b"binary mock")
            found = locator.locate_prism(
                allow_picker=False,
                module_file=str(root / "prism_discovery.py"),
                env={"BOTWCRAFT_PRISM": str(exe)})
            self.assertEqual(found, exe.resolve())

    def test_no_prism_returns_none_without_picker(self):
        with TemporaryDirectory() as d:
            self.assertIsNone(locator.locate_prism(
                allow_picker=False, module_file=str(Path(d) / "prism_discovery.py"),
                env={"PATH": "", "LOCALAPPDATA": str(Path(d) / "missing")}))

    def test_relocated_instance_root_config(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            data = root / "PrismLauncher"
            data.mkdir()
            moved = root / "custom" / "instances"
            moved.mkdir(parents=True)
            (data / "prismlauncher.cfg").write_text("InstanceDir=" + str(moved) + "\n")
            self.assertEqual(locator.prism_instance_dir(data, "BotwCraftNative"),
                             moved / "BotwCraftNative")

    def test_modern_game_dir_wins_over_stale_dot_minecraft(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".minecraft").mkdir()
            (root / "minecraft").mkdir()
            self.assertEqual(locator.prism_minecraft_dir(root), root / "minecraft")

if __name__ == "__main__":
    unittest.main()
