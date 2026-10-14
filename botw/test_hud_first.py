"""Guard first SkyCraft HUD milestone against accidental old takeover paths."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent.parent
CLIENT = ROOT / "fabric/src/client/java/dev/skycraft/client"

class HudFirstTests(unittest.TestCase):
    def test_real_frame_exporter_is_used(self):
        source=(CLIENT/"SkyClient.java").read_text(encoding="utf-8")
        self.assertIn("FrameExporter.capture(minecraft)",source)
        self.assertIn("BotwCraftSession.hudEnabled()",source)
        renderer=(CLIENT/"mixin/LevelRendererMixin.java").read_text(encoding="utf-8")
        self.assertIn("SkyClient.hudCaptureActive()",renderer)
        self.assertNotIn("if (SkyClient.linked()",renderer)

    def test_hud_command_does_not_take_focus(self):
        source=(CLIENT/"SkyCraftClient.java").read_text(encoding="utf-8")
        self.assertIn('literal("hud")',source)
        self.assertIn('BotwCraftSession.setHudEnabled(true)',source)
        self.assertIn('BotwCraftSession.setHudEnabled(false)',source)
        ctl=(CLIENT/"BotwCraftSession.java").read_text(encoding="utf-8")
        self.assertIn("hudEnabled = false;",ctl)
        self.assertNotIn("SDL_HideWindow",ctl)
        self.assertNotIn("requestTeleport",ctl)
        self.assertNotIn("InputBridge.drain",ctl)

    def test_external_hud_window_cannot_steal_keyboard(self):
        source=(ROOT/"botw/hud_overlay.py").read_text(encoding="utf-8")
        self.assertIn("WS_EX_NOACTIVATE",source)
        self.assertIn("WS_EX_TRANSPARENT",source)
        self.assertIn("WS_EX_LAYERED",source)

if __name__=="__main__":
    unittest.main()
