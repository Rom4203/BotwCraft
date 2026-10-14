"""Regression tests: BotwCraft connection cannot silently take over Minecraft.

These tests protect users' saves and input against reintroducing SkyCraft's
Skyrim-only code paths while native BOTW terrain/collision remains unavailable.
"""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent.parent
CLIENT = ROOT / "fabric/src/client/java/dev/skycraft/client"


class ManualOnlyTests(unittest.TestCase):
    def test_bridge_supervisor_does_not_launch_prism(self):
        launcher = (ROOT / "botw/launcher.py").read_text(encoding="utf-8")
        self.assertNotIn("prismlauncher.exe", launcher)
        self.assertNotIn("start_minecraft(", launcher)
        self.assertNotIn("JAVA_TOOL_OPTIONS", launcher)
        self.assertNotIn("control_bridge.py", launcher)

    def test_client_does_not_mutate_world_or_input(self):
        source = (CLIENT / "SkyClient.java").read_text(encoding="utf-8")
        forbidden = (
            "requestTeleport(", "teleportTo(", "player.setPos(",
            "player.setYRot(", "hideWindowOnce(", "SDL_HideWindow(",
            "InputBridge.releaseAll(",
            "MirrorWorld.openWhenReady(", "applyLinkedOptions(",
            "minecraft.options.save(", "skycraft$skipLevel("
        )
        for token in forbidden:
            with self.subTest(token=token):
                self.assertNotIn(token, source)
        self.assertIn("return false;", source)
        self.assertIn("WorldExporter.frame(", source)
        self.assertIn("if (BotwCraftSession.compositorInputs() && SkyLink.transportOpen())", source)
        self.assertIn("InputBridge.drain(Minecraft.getInstance())", source)
        session = (CLIENT / "BotwCraftSession.java").read_text(encoding="utf-8")
        self.assertIn("private static volatile boolean compositorInputs;", session)
        self.assertIn("if (enabled && !requested)", session)

    def test_no_automatic_server_rules_or_starter_items(self):
        source = (ROOT / "fabric/src/main/java/dev/skycraft/SkyCraft.java").read_text(encoding="utf-8")
        self.assertNotIn("configureServer(", source)
        self.assertNotIn("giveStarterKit(", source)
        self.assertNotIn("giveBuilderKit(", source)
        self.assertNotIn("ServerLifecycleEvents.SERVER_STARTED", source)
        self.assertNotIn("ServerPlayConnectionEvents.JOIN", source)

    def test_status_displays_actual_link_position(self):
        session = (CLIENT / "BotwCraftSession.java").read_text(encoding="utf-8")
        self.assertIn("SkyLink.readSkyState(snapshot)", session)
        self.assertIn("snapshot.x, snapshot.y, snapshot.z", session)
        self.assertIn("aucun TP", session)


if __name__ == "__main__":
    unittest.main()
