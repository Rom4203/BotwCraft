"""Verify offline preview ZIP and isolated Prism setup without real accounts."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest
import zipfile

import package_preview
from botw import install_preview

CONTENTS = (
    "fabric/build/libs/skycraft-0.1.2.jar",
    "botw/host_bridge.py",
    "botw/control_bridge.py",
    "botw/hud_overlay.py",
    "botw/launcher.py",
    "botw/prism_discovery.py",
    "packaging/INSTALL_AND_PREVIEW.bat",
    "packaging/PREVIEW_BLOCKS.bat",
    "botw/install_preview.py",
    "tools/minecraft-bundle/Prism/instances/SkyCraft/instance.cfg",
    "tools/minecraft-bundle/Prism/instances/SkyCraft/mmc-pack.json",
    "packaging/README_PREVIEW.txt",
    "LICENSE",
    "THIRD-PARTY-NOTICES.md",
)

class Tests(unittest.TestCase):
    @staticmethod
    def make_source(path):
        for name in CONTENTS:
            target = path / name
            target.parent.mkdir(parents=True, exist_ok=True)
            if name.endswith("instance.cfg"):
                target.write_text("[General]\nname=SkyCraft\nJvmArgs=--enable-native-access=ALL-UNNAMED -Dskycraft.startHidden=true\n")
            else:
                target.write_bytes(b"synthetic unit-test data; not a Nintendo asset")

    def test_package_contains_compiled_minecraft_without_switch_exefs(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_source(root)
            result = package_preview.build(root=root)
            with zipfile.ZipFile(result) as archive:
                self.assertIsNone(archive.testzip())
                names = archive.namelist()
                self.assertEqual(len(names), len(CONTENTS) + 1)
                self.assertIn("prism_discovery.py", names)
                self.assertIn("bridge/prism_discovery.py", names)
                self.assertIn("minecraft_mods/skycraft-0.1.2.jar", names)
                self.assertIn("INSTALL_AND_PREVIEW.bat", names)
                self.assertFalse(any("subsdk9" in n or "botwcraft.wxlm" in n for n in names))

    def test_no_fabric_artifact_means_no_misleading_release(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_source(root)
            (root / "fabric/build/libs/skycraft-0.1.2.jar").unlink()
            with self.assertRaises(FileNotFoundError):
                package_preview.build(root=root)
            self.assertFalse((root / "dist/BotwCraft-Blocks-Preview.zip").exists())

    def test_install_updates_dedicated_prism_instance_only(self):
        with TemporaryDirectory() as directory:
            root = Path(directory) / "preview"
            source = Path(directory) / "source"
            self.make_source(source)
            package_preview.build(root=source)
            root.mkdir()
            with zipfile.ZipFile(source / "dist/BotwCraft-Blocks-Preview.zip") as z:
                z.extractall(root)
            instance = Path(directory) / "PrismLauncher" / "instances" / "BotwCraftPreview"
            with patch.object(install_preview, "download_fabric_api", return_value=None):
                install_preview.install(root, instance)
                install_preview.install(root, instance)  # idempotent
            self.assertTrue((instance / ".minecraft/mods/skycraft-0.1.2.jar").exists())
            self.assertTrue((instance / ".minecraft/botwcraft.preview").is_file())
            cfg = (instance / "instance.cfg").read_text()
            self.assertIn("name=BotwCraftPreview", cfg)
            self.assertIn("-Dbotwcraft.experimentalBlocks=true", cfg)

    def test_existing_manual_prism_profile_gets_preview_java_flags(self):
        existing = ("[General]\nname=BotwCraftPreview\n"
                    "OverrideJavaArgs=false\n"
                    "JvmArgs=-Xmx3G -Dskycraft.startHidden=true\n"
                    "MinMemAlloc=512\n")
        out = install_preview.preview_jvm_config(existing)
        self.assertIn("OverrideJavaArgs=true", out)
        self.assertIn("-Xmx3G", out)
        self.assertIn("--enable-native-access=ALL-UNNAMED", out)
        self.assertIn("-Dbotwcraft.experimentalBlocks=true", out)
        self.assertIn("-Dskycraft.startHidden=false", out)
        self.assertIn("-Dskycraft.showWindow=true", out)
        self.assertNotIn("-Dskycraft.startHidden=true", out)
        self.assertIn("MinMemAlloc=512", out)
        self.assertEqual(out, install_preview.preview_jvm_config(out))
        self.assertEqual(out.count("JvmArgs="), 1)

    def test_fabric_version_selection_requires_jar(self):
        candidate = dict(date_published="2026-10-09", files=[
            dict(primary=True, filename="fabric-api-test.jar", url="https://cdn.modrinth.com/file.jar")])
        chosen = install_preview.modrinth_fabric_version([candidate])
        self.assertEqual(chosen["filename"], "fabric-api-test.jar")
        with self.assertRaises(ValueError):
            install_preview.modrinth_fabric_version([])

if __name__ == "__main__":
    unittest.main()
