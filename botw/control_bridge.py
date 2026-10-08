"""Windows keyboard -> SkyCraft Fabric input + MC-physics -> virtual BOTW pad.

A transport/prototype component, not yet a playable native BOTW/Minecraft mod.
Uses only localhost. A virtual X360 pad needs vgamepad + ViGEmBus installed,
then configured as Player 1 in Ryujinx. It never edits Ryujinx's files.
"""
from __future__ import annotations

import argparse
import ctypes
import json
import math
import socket
import sys
import time
from dataclasses import dataclass

# Win32 virtual-key -> SDL3 scancode used by Minecraft/SkyCraft.
SDL_KEYS = {
    0x57: 26, 0x41: 4, 0x53: 22, 0x44: 7,      # WASD
    0x20: 44, 0xA0: 225, 0xA2: 224,           # space, left shift, left ctrl
    0x45: 8, 0x51: 20, 0x52: 21,              # E, Q, R
    0x09: 43, 0x1B: 41, 0x74: 62,            # Tab, Escape, F5
    **{0x31 + i: 30 + i for i in range(9)},  # 1..9
}
MOUSE = {0x01: 1, 0x02: 3}                    # SDL mouse left=1, right=3
IN_KEY, IN_MOUSE_BUTTON, IN_RELEASE_ALL = 1, 2, 6
MC_IN_WORLD, MC_SCREEN_OPEN, MC_ON_GROUND, MC_SNEAKING, MC_SPRINTING = 1, 2, 4, 8, 16
RAW_KEYBOARD = ("W", "A", "S", "D", "SPACE", "SHIFT", "CTRL", "E")
VK_CONTROL = {"W": 0x57, "A": 0x41, "S": 0x53, "D": 0x44,
              "SPACE": 0x20, "SHIFT": 0xA0, "CTRL": 0xA2, "E": 0x45}

def key_events(previous: set[int], current: set[int]):
    """Generate SkyCraft key/button transitions; no auto-repeating held keys."""
    events = []
    for vk, scancode in sorted(SDL_KEYS.items()):
        if (vk in previous) != (vk in current):
            events.append([IN_KEY, scancode, int(vk in current), 0, 0])
    for vk, button in sorted(MOUSE.items()):
        if (vk in previous) != (vk in current):
            events.append([IN_MOUSE_BUTTON, button, int(vk in current), 0, 0])
    return events

@dataclass(frozen=True)
class GamepadState:
    right: float = 0.0
    forward: float = 0.0
    jump: bool = False
    sprint: bool = False
    crouch: bool = False
    interact: bool = False

def _clamp(value: float):
    return max(-1.0, min(1.0, value))

def raw_gamepad(pressed: set[int]):
    right = int(0x44 in pressed) - int(0x41 in pressed)
    forward = int(0x57 in pressed) - int(0x53 in pressed)
    d = math.hypot(right, forward)
    if d > 1:
        right, forward = right / d, forward / d
    return GamepadState(right, forward, 0x20 in pressed, 0xA0 in pressed,
                        0xA2 in pressed, 0x45 in pressed)

def mc_gamepad(previous: dict, current: dict, seconds: float,
               max_walk_speed: float = 4.3):
    """Minecraft planar feet movement -> camera-relative joystick intent.

    Both points are in Minecraft X/Z coordinates, +Z is south. Yaw degrees
    follow Minecraft convention (0=south, 90=west). This is *velocity intent*,
    not a trustworthy BOTW player transform or a terrain/collision proxy.
    """
    if not (0.005 < seconds < 0.5) or not (current.get("flags", 0) & MC_IN_WORLD):
        return None
    if not (previous.get("flags", 0) & MC_IN_WORLD):
        return None
    if current.get("frame", 0) <= previous.get("frame", 0):
        return None
    values = tuple(current.get(k) for k in ("x", "y", "z", "yaw"))
    prev_values = tuple(previous.get(k) for k in ("x", "z"))
    if not all(type(v) in (float, int) and math.isfinite(v) for v in values + prev_values):
        return None
    dx = (current["x"] - previous["x"]) / seconds
    dz = (current["z"] - previous["z"]) / seconds
    if math.hypot(dx, dz) > 25.0:   # teleport / chunk load; never drive the pad
        return None
    yaw = math.radians(current["yaw"])
    right = (dx * math.cos(yaw) + dz * math.sin(yaw)) / max_walk_speed
    forward = (-dx * math.sin(yaw) + dz * math.cos(yaw)) / max_walk_speed
    norm = math.hypot(right, forward)
    if norm > 1:
        right /= norm
        forward /= norm
    return GamepadState(_clamp(right), _clamp(forward),
                        not bool(current["flags"] & MC_ON_GROUND),
                        bool(current["flags"] & MC_SPRINTING),
                        bool(current["flags"] & MC_SNEAKING),
                        False)

def bridge_request(packet, port=39847):
    data = (json.dumps(packet, separators=(",", ":")) + "\n").encode("utf-8")
    with socket.create_connection(("127.0.0.1", port), timeout=0.35) as client:
        client.settimeout(0.35)
        client.sendall(data)
        reply = client.makefile("rb").readline(4096)
        if not reply:
            raise OSError("bridge closed without replying")
        obj = json.loads(reply)
        if not obj.get("ok"):
            raise ValueError(obj.get("error", "bridge refused packet"))
        return obj

class VirtualController:
    def __init__(self):
        try:
            import vgamepad as vg
            self.vg = vg
            self.pad = vg.VX360Gamepad()
        except (ImportError, OSError) as exc:
            raise RuntimeError("vgamepad and ViGEmBus are required for the BOTW controller") from exc

    def write(self, state):
        vg = self.vg
        p = self.pad
        p.left_joystick_float(x_value_float=state.right, y_value_float=state.forward)
        for active, button in (
            (state.jump, vg.XUSB_BUTTON.XUSB_GAMEPAD_X),
            (state.sprint, vg.XUSB_BUTTON.XUSB_GAMEPAD_B),
            (state.crouch, vg.XUSB_BUTTON.XUSB_GAMEPAD_LEFT_THUMB),
            (state.interact, vg.XUSB_BUTTON.XUSB_GAMEPAD_A),
        ):
            if active:
                p.press_button(button=button)
            else:
                p.release_button(button=button)
        p.update()

    def reset(self):
        self.pad.reset()
        self.pad.update()

class WinKeys:
    def __init__(self):
        self.api = ctypes.windll.user32
        self.api.GetForegroundWindow.restype = ctypes.c_void_p

    def ryujinx_focused(self):
        handle = self.api.GetForegroundWindow()
        if not handle:
            return False
        buffer = ctypes.create_unicode_buffer(512)
        self.api.GetWindowTextW(handle, buffer, 512)
        return "ryujinx" in buffer.value.lower()

    def pressed(self):
        return {vk for vk in (*SDL_KEYS, *MOUSE)
                if self.api.GetAsyncKeyState(vk) & 0x8000}

def run(port=39847, controller=True):
    if sys.platform != "win32":
        raise RuntimeError("Windows required for physical key sampling and virtual X360 controller")
    input_api = WinKeys()
    pad = None
    if controller:
        try:
            pad = VirtualController()
            print("[BotwCraft] Xbox controller created; select it in Ryujinx Player 1", flush=True)
        except RuntimeError as exc:
            print(f"[BotwCraft] No virtual controller: {exc}", flush=True)
            print("[BotwCraft] Keyboard events can still reach the Minecraft bridge.", flush=True)
    prior = set()
    last_mc = None
    last_mc_time = None
    try:
        print("[BotwCraft] Input sync running. Focus Ryujinx; Ctrl+C here to stop.", flush=True)
        while True:
            focused = input_api.ryujinx_focused()
            current = input_api.pressed() if focused else set()
            events = key_events(prior, current)
            prior = current
            if events:
                try:
                    bridge_request({"type": "input", "events": events}, port)
                except (OSError, ValueError):
                    pass
            status = None
            if focused:
                try:
                    status = bridge_request({"type": "minecraft"}, port)["minecraft"]
                except (OSError, ValueError, KeyError):
                    pass
            now = time.monotonic()
            state = raw_gamepad(current)
            if status and (status.get("flags", 0) & MC_IN_WORLD) and last_mc:
                derived = mc_gamepad(last_mc, status, now - last_mc_time)
                if derived is not None:
                    # Explicit Minecraft physics mode when updates are flowing.
                    state = GamepadState(derived.right, derived.forward,
                                         state.jump, state.sprint, state.crouch, state.interact)
            if status and status.get("in_world") and status.get("frame") != (last_mc or {}).get("frame"):
                last_mc, last_mc_time = status, now
            elif not focused:
                last_mc, last_mc_time = None, None
            if pad:
                pad.write(state if focused else GamepadState())
            time.sleep(1/60)
    except KeyboardInterrupt:
        pass
    finally:
        if pad:
            pad.reset()
        if prior:
            try:
                bridge_request({"type":"input","events":[[IN_RELEASE_ALL,0,0,0,0]]},port)
            except (OSError,ValueError):
                pass

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=39847)
    parser.add_argument("--no-controller", action="store_true")
    args = parser.parse_args()
    try:
        run(args.port, not args.no_controller)
    except RuntimeError as exc:
        raise SystemExit(f"[BotwCraft] {exc}")
