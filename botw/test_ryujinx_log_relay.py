"""Tests for log-driven BOTW host telemetry."""
import json
import socketserver
import threading
import unittest
from botw.ryujinx_log_relay import parse_pose, forward_pose

class Receiver(socketserver.StreamRequestHandler):
    def handle(self):
        self.server.records.append(json.loads(self.rfile.readline()))
        self.wfile.write(b'{"ok":true}\n')

class Tests(unittest.TestCase):
    def test_guest_format(self):
        p = parse_pose("[INFO] [BotwCraft:v100] position X=-10 Y=20 Z=30")
        self.assertEqual((p["x"], p["y"], p["z"]), (-10, 20, 30))
    def test_invalid_lines(self):
        self.assertIsNone(parse_pose("plain X=1 Y=2 Z=3"))
        self.assertIsNone(parse_pose("[BotwCraft:v100] X=1000000 Y=0 Z=0"))
    def test_tcp_roundtrip(self):
        with socketserver.TCPServer(("127.0.0.1", 0), Receiver) as server:
            server.records=[]
            thread=threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                pose=parse_pose("[BotwCraft:v100] X=1.5 Y=2 Z=3")
                self.assertTrue(forward_pose(pose, server.server_address[1]))
                self.assertEqual(server.records[0]["x"], 1.5)
            finally:
                server.shutdown()
                thread.join(2)

if __name__ == "__main__":
    unittest.main()
