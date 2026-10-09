"""Synthetic offline tests for the REAL native SkyCraft Minecraft profile."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

from botw import install_native_mc


class NativeMinecraftProfileTests(unittest.TestCase):
    def test_profile_jvm_args_are_native_not_preview(self):
        original = ("[General]\nname=SkyCraft\n"
                    "OverrideJavaArgs=false\n"
                    "JvmArgs=-Xmx4G -Dbotwcraft.experimentalBlocks=true "
                    "-Dskycraft.startHidden=true\n")
        updated = install_native_mc.native_instance_cfg(original)
        self.assertIn("name=BotwCraftNative", updated)
        self.assertIn("-Xmx4G", updated)
        self.assertIn("-Dskycraft.startHidden=false", updated)
        self.assertIn("-Dskycraft.quitWithSkyrim=false", updated)
        self.assertIn("--enable-native-access=ALL-UNNAMED", updated)
        self.assertIn("-Dbotwcraft.experimentalBlocks=false", updated)
        self.assertNotIn("-Dbotwcraft.experimentalBlocks=true", updated)
        self.assertEqual(updated, install_native_mc.native_instance_cfg(updated))

    def test_isolated_native_profile_contains_mod_and_keeps_original_instance(self):
        with TemporaryDirectory() as directory:
            base = Path(directory)
            prism = base / "PrismLauncher" / "prismlauncher.exe"
            prism.parent.mkdir()
            prism.write_bytes(b"Prism executable placeholder")
            bundle = base / "bundle"
            template = bundle / "prism_template"
            template.mkdir(parents=True)
            (template / "instance.cfg").write_text(
                "[General]\nname=SkyCraft\nJvmArgs=-Xmx4G\n",
                encoding="utf-8")
            (template / "mmc-pack.json").write_text("{}")
            mods = bundle / "minecraft_mods"
            mods.mkdir()
            (mods / "skycraft-1.0.jar").write_bytes(b"compiled test jar")
            data_root = base / "PrismData"
            env = {"BOTWCRAFT_PRISM_DIR": str(data_root)}
            with patch.dict("os.environ", env, clear=False):
                native = install_native_mc.install_native_minecraft(
                    bundle, prism=prism, skip_fabric_download=True)
            self.assertEqual(native.name, "BotwCraftNative")
            self.assertTrue((native / "minecraft/mods/skycraft-1.0.jar").exists())
            self.assertFalse((native / "minecraft/botwcraft.preview").exists())
            self.assertIn("-Dbotwcraft.experimentalBlocks=false", (native / "instance.cfg").read_text())
            self.assertTrue((native / "mmc-pack.json").exists())

    def test_rejects_preview_marker(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            prism = root / "prismlauncher.exe"
            prism.write_bytes(b"exe")
            template = root / "bundle/prism_template"
            template.mkdir(parents=True)
            (template / "instance.cfg").write_text("[General]\nname=SkyCraft\n")
            (template / "mmc-pack.json").write_text("{}")
            mods = root / "bundle/minecraft_mods"
            mods.mkdir()
            (mods / "skycraft-1.0.jar").write_bytes(b"jar")
            data = root / "prism-data"
            game = data / "instances/BotwCraftNative/.minecraft"
            game.mkdir(parents=True)
            (game / "botwcraft.preview").touch()
            with patch.dict("os.environ", {"BOTWCRAFT_PRISM_DIR": str(data)},
                            clear=False):
                with self.assertRaises(RuntimeError):
                    install_native_mc.install_native_minecraft(
                        root / "bundle", prism=prism,
                        skip_fabric_download=True)


    def test_existing_prism_11_minecraft_dir_is_used(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            prism = root / "prismlauncher.exe"
            prism.write_bytes(b"exe")
            bundle = root / "bundle"
            template = bundle / "prism_template"
            template.mkdir(parents=True)
            (template / "instance.cfg").write_text(
                "[General]\nname=SkyCraft\nJvmArgs=-Dbotwcraft.experimentalBlocks=true\n")
            (template / "mmc-pack.json").write_text("{}")
            (bundle / "minecraft_mods").mkdir()
            (bundle / "minecraft_mods" / "skycraft-1.0.jar").write_bytes(b"compiled jar")
            data = root / "data"
            data.mkdir()
            relocated = root / "D-drive" / "prism" / "instances"
            relocated.mkdir(parents=True)
            (data / "prismlauncher.cfg").write_text("InstanceDir=" + str(relocated) + "\n")
            profile = relocated / "BotwCraftNative"
            real = profile / "minecraft"
            real.mkdir(parents=True)
            (real / "mods").mkdir()
            old = real / "mods" / "skycraft-0.0.jar"
            old.write_bytes(b"old")
            with patch.dict("os.environ", {"BOTWCRAFT_PRISM_DIR": str(data)}, clear=False):
                installed = install_native_mc.install_native_minecraft(
                    bundle, prism=prism, skip_fabric_download=True)
            self.assertEqual(installed, profile)
            self.assertTrue((real / "mods" / "skycraft-1.0.jar").is_file())
            self.assertFalse(old.exists())
            self.assertFalse((profile / ".minecraft").exists())
            cfg = (profile / "instance.cfg").read_text()
            self.assertIn("-Dbotwcraft.experimentalBlocks=false", cfg)


if __name__ == "__main__":
    unittest.main()
