"""Offline protocol conformance checks against the SkyCraft v11 C++ layout."""
import json
import socket
import struct
import threading
import unittest

from botw import host_bridge

class FakeClock:
    def __init__(self):
        self.now = 100000
    def __call__(self):
        return self.now

class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.mem = bytearray(0x400)
        self.bridge = host_bridge.Bridge(memory=self.mem, clock=self.clock)

    def test_mapping_header_layout(self):
        self.assertEqual(struct.unpack_from("<II", self.mem, 0),
                         (host_bridge.MAGIC, host_bridge.VERSION))
        self.assertEqual(struct.unpack_from("<Q", self.mem, 16)[0], 0)

    def test_no_phantom_heartbeat_before_first_position(self):
        self.assertFalse(self.bridge.heartbeat())
        self.assertEqual(struct.unpack_from("<Q", self.mem, 16)[0], 0)

    def test_seqlock_position_and_skycraft_layout(self):
        self.bridge.update(dict(type="pose", x=-10.5, y=250, z=31,
                                yaw=90, pitch=10, world=5))
        self.assertEqual(struct.unpack_from("<I", self.mem, 0x100)[0], 2)
        self.assertEqual(struct.unpack_from("<III", self.mem, 0x104), (1, 5, 1))
        self.assertEqual(struct.unpack_from("<3d", self.mem, 0x110), (-10.5, 250, 31))
        self.assertEqual(struct.unpack_from("<2f", self.mem, 0x128), (90, 10))
        self.assertEqual(struct.unpack_from("<III", self.mem, 0x130), (1, 1280, 720))
        self.assertEqual(struct.unpack_from("<Q", self.mem, 16)[0], self.clock.now)
        self.assertTrue(self.bridge.heartbeat())

    def test_world_change_triggers_mc_teleport_epoch(self):
        def packet(world):
            return dict(type="pose", x=1, y=2, z=3, yaw=0, pitch=0, world=world)
        self.bridge.update(packet(1))
        self.bridge.update(packet(1))
        self.assertEqual(struct.unpack_from("<I", self.mem, 0x130)[0], 1)
        self.bridge.update(packet(2))
        self.assertEqual(struct.unpack_from("<I", self.mem, 0x130)[0], 2)
        self.assertEqual(struct.unpack_from("<I", self.mem, 0x10C)[0], 2)

    def test_stale_pose_disables_game_and_heartbeat(self):
        self.bridge.update(dict(type="pose", x=1, y=2, z=3, yaw=0, pitch=0))
        self.clock.now += 1050
        self.assertFalse(self.bridge.heartbeat())
        self.assertEqual(struct.unpack_from("<I", self.mem, 0x104)[0], 0)
        self.assertEqual(struct.unpack_from("<Q", self.mem, 16)[0], 0)

    def test_reject_invalid_or_fabricated_state(self):
        base = dict(type="pose", x=1, y=2, z=3, yaw=0, pitch=0)
        for key, value in [("x", "not-a-number"), ("x", True),
                           ("y", float("nan")), ("z", float("inf")),
                           ("world", -1), ("world", 1.5)]:
            data = dict(base, **{key: value})
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                self.bridge.update(data)
        self.assertEqual(struct.unpack_from("<Q", self.mem, 16)[0], 0)

    def test_mc_state_readback(self):
        struct.pack_into("<II3d", self.mem, 0x200, 12, 5, 2.0, 3.0, 4.0)
        self.assertEqual(self.bridge.minecraft_status(),
                         dict(seq=12, flags=5, x=2.0, y=3.0, z=4.0))

    def test_loopback_transport(self):
        with host_bridge.Server(("127.0.0.1", 0), host_bridge.Client) as server:
            server.bridge = self.bridge
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            try:
                with socket.create_connection(server.server_address, timeout=2) as sock:
                    sock.sendall((json.dumps(dict(type="pose", x=1, y=2, z=3,
                                                 yaw=0, pitch=0)) + "\n").encode())
                    response = json.loads(sock.makefile("rb").readline())
                self.assertTrue(response["ok"])
                self.assertEqual(struct.unpack_from("<3d", self.mem, 0x110),
                                 (1.0, 2.0, 3.0))
            finally:
                server.shutdown()
                worker.join(3)

if __name__ == "__main__":
    unittest.main()
