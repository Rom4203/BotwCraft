"""Pure host input tests (no Ryujinx, driver, or Minecraft required)."""
import json
import math
import socket
import threading
import unittest

from botw import control_bridge, host_bridge

class ControlTests(unittest.TestCase):
    def test_wasd_sdl_translation_and_key_releases(self):
        events = control_bridge.key_events(set(), {0x57, 0x20, 0x01})
        self.assertIn([1, 26, 1, 0, 0], events)
        self.assertIn([1, 44, 1, 0, 0], events)
        self.assertIn([2, 1, 1, 0, 0], events)
        self.assertEqual(control_bridge.key_events({0x57}, {0x57}), [])
        self.assertIn([1, 26, 0, 0, 0],
                      control_bridge.key_events({0x57}, set()))

    def test_mouse_camera_delta_uses_virtual_cursor_no_jump(self):
        events, stick, virt = control_bridge.mouse_events(None, (900, 400), (0, 0))
        self.assertEqual(events, [])
        self.assertEqual(virt, (0, 0))
        events, stick, virt = control_bridge.mouse_events((900, 400), (920, 390), virt)
        self.assertEqual(events, [[4, 0, 20, -10, 0]])
        self.assertAlmostEqual(stick[0], 0.8)
        self.assertAlmostEqual(stick[1], 0.4)
        self.assertEqual(virt, (20, -10))

    def test_mouse_input_clamps_large_jumps(self):
        events, stick, _ = control_bridge.mouse_events((0, 0), (9999, -9999), (0, 0))
        self.assertEqual(events, [[4, 0, 80, -80, 0]])
        self.assertEqual(stick, (1.0, 1.0))

    def test_keyboard_gamepad_axes_normalized(self):
        state = control_bridge.raw_gamepad({0x57, 0x44, 0x20})
        self.assertAlmostEqual(state.right, math.sqrt(0.5))
        self.assertAlmostEqual(state.forward, math.sqrt(0.5))
        self.assertTrue(state.jump)
        self.assertEqual(control_bridge.raw_gamepad({0x57, 0x53}).forward, 0.0)

    def test_minecraft_velocity_to_camera_relative_joystick(self):
        old = dict(frame=1, flags=1, x=0., y=1., z=0., yaw=0.)
        current = dict(frame=2, flags=1, x=0., y=1., z=0.43, yaw=0.)
        state = control_bridge.mc_gamepad(old, current, 0.1)
        self.assertAlmostEqual(state.forward, 1.0)
        self.assertAlmostEqual(state.right, 0.0)
        west = dict(frame=2, flags=1, x=-0.43, y=1., z=0., yaw=90.)
        state = control_bridge.mc_gamepad(old, west, 0.1)
        self.assertAlmostEqual(state.forward, 1.0)
        self.assertAlmostEqual(state.right, 0.0)

    def test_stale_teleport_and_inactive_are_rejected(self):
        old = dict(frame=1, flags=1, x=0., y=0., z=0., yaw=0.)
        self.assertIsNone(control_bridge.mc_gamepad(
            old, dict(frame=1, flags=1, x=0., y=0., z=1., yaw=0.), 0.1))
        self.assertIsNone(control_bridge.mc_gamepad(
            old, dict(frame=2, flags=1, x=0., y=0., z=100., yaw=0.), 0.1))
        self.assertIsNone(control_bridge.mc_gamepad(
            old, dict(frame=2, flags=0, x=0., y=0., z=0.1, yaw=0.), 0.1))

    def test_real_host_tcp_ring_compatibility(self):
        memory = bytearray(0x12000)
        bridge = host_bridge.Bridge(memory=memory)
        with host_bridge.Server(("127.0.0.1", 0), host_bridge.Client) as server:
            server.bridge = bridge
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            try:
                reply = control_bridge.bridge_request(
                    {"type": "input", "events": [[1, 26, 1, 0, 0]]},
                    port=server.server_address[1])
                self.assertEqual(reply["queued"], 1)
                self.assertEqual(bridge.push_inputs([]), 0)
            finally:
                server.shutdown()
                worker.join(3)

if __name__ == "__main__":
    unittest.main()
