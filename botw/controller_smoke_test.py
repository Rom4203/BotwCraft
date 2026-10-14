"""BotwCraft input-only smoke test for Windows / Ryujinx.

Requires: pip install vgamepad
On Windows, vgamepad uses the ViGEmBus virtual-controller driver.
This is NOT Minecraft integration or a BOTW memory mod.
"""
from __future__ import annotations

import argparse
import ctypes
import sys
import time
from dataclasses import dataclass

VK = {"W": 0x57, "A": 0x41, "S": 0x53, "D": 0x44,
      "SPACE": 0x20, "SHIFT": 0x10, "CTRL": 0x11,
      "E": 0x45, "Q": 0x51, "ESC": 0x1B}
KEYS = tuple(VK)

@dataclass(frozen=True)
class PadState:
    x: float = 0.0
    y: float = 0.0
    jump: bool = False
    sprint: bool = False
    crouch: bool = False
    interact: bool = False

def mapped_state(pressed: set[str]) -> PadState:
    x = float(("D" in pressed) - ("A" in pressed))
    y = float(("W" in pressed) - ("S" in pressed))
    if x and y:
        x *= 0.7071067811865476
        y *= 0.7071067811865476
    return PadState(x, y, "SPACE" in pressed, "SHIFT" in pressed,
                    "CTRL" in pressed, "E" in pressed)

def get_keys() -> set[str]:
    api = ctypes.windll.user32
    return {name for name, code in VK.items()
            if api.GetAsyncKeyState(code) & 0x8000}

def apply_state(pad, vg, state: PadState):
    pad.left_joystick_float(x_value_float=state.x, y_value_float=state.y)
    for pressed, button in (
        (state.jump, vg.XUSB_BUTTON.XUSB_GAMEPAD_X),
        (state.sprint, vg.XUSB_BUTTON.XUSB_GAMEPAD_B),
        (state.crouch, vg.XUSB_BUTTON.XUSB_GAMEPAD_LEFT_THUMB),
        (state.interact, vg.XUSB_BUTTON.XUSB_GAMEPAD_A)):
        if pressed:
            pad.press_button(button=button)
        else:
            pad.release_button(button=button)
    pad.update()

def run() -> int:
    if sys.platform != "win32":
        print("This controller test requires Windows.")
        return 2
    try:
        import vgamepad as vg
        pad = vg.VX360Gamepad()
    except Exception as exc:
        print("Cannot create virtual controller:", exc)
        print("Run 'py -m pip install vgamepad' and install its required ViGEmBus driver.")
        return 2
    print("Virtual Xbox 360 controller created.")
    print("In Ryujinx map Player 1 to this controller (Pro Controller layout).")
    print("WASD = left stick, SPACE = X (jump), SHIFT = B (run), CTRL = stick click, E = A (interact).")
    print("Focus Ryujinx to play. Press ESC to exit the controller test.")
    print("WARNING: BOTW menus may map buttons differently depending on your Ryujinx profile.")
    try:
        while True:
            keys = get_keys()
            if "ESC" in keys:
                break
            apply_state(pad, vg, mapped_state(keys))
            time.sleep(1 / 60)
    except KeyboardInterrupt:
        pass
    finally:
        pad.reset()
        pad.update()
    return 0

if __name__ == "__main__":
    raise SystemExit(run())
