"""Regression: Rust third-window owns focus, Minecraft 26.3 stays active only
when the user explicitly opts in, and SDL never steals physical mouse input."""
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parent.parent
CLIENT=ROOT/"fabric/src/client/java/dev/skycraft/client"

class CompositorFocusTests(unittest.TestCase):
    def test_focus_only_in_explicit_compositor_session(self):
        session=(CLIENT/"BotwCraftSession.java").read_text(encoding="utf8")
        window=(CLIENT/"mixin/WindowMixin.java").read_text(encoding="utf8")
        input_constants=(CLIENT/"mixin/InputConstantsMixin.java").read_text(encoding="utf8")
        client=(CLIENT/"SkyClient.java").read_text(encoding="utf8")
        self.assertIn("previouslyPauseOnLostFocus = minecraft.options.pauseOnLostFocus",session)
        self.assertIn("minecraft.options.pauseOnLostFocus = false",session)
        self.assertIn("minecraft.options.pauseOnLostFocus = previouslyPauseOnLostFocus",session)
        self.assertIn("setCompositorInputs(false)",session)
        self.assertIn("return BotwCraftSession.compositorInputs();",client)
        self.assertIn("cir.setReturnValue(SkyClient.tookOver())",window)
        self.assertIn("if (SkyClient.tookOver())",input_constants)
        self.assertIn("ci.cancel()",input_constants)
        self.assertNotIn("minecraft.options.save()",session)

    def test_mouse_menu_and_fps_remain_distinct(self):
        bridge=(CLIENT/"InputBridge.java").read_text(encoding="utf8")
        proto=(ROOT/"fabric/src/main/java/dev/skycraft/link/Proto.java").read_text(encoding="utf8")
        client=(CLIENT/"SkyClient.java").read_text(encoding="utf8")
        self.assertIn("IN_MOUSE_DELTA = 9",proto)
        self.assertIn("case Proto.IN_MOUSE_DELTA",bridge)
        self.assertIn("minecraft.mouseHandler.onMove(handle, cursorX, cursorY, a, b)",bridge)
        self.assertIn("minecraft.gui.screen() == null ? 0x10000",client)
        self.assertIn("BotwCraftSession.compositorInputs() ? 0x20000",client)
        self.assertIn("InputBridge.drain(Minecraft.getInstance())",client)

if __name__=="__main__":
    unittest.main()
