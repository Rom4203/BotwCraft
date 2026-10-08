"""BotwCraft Windows host bridge: SkyCraft-compatible memory owner.

Transport: newline-delimited JSON over localhost TCP for a future Ryujinx
guest mod/host adapter. Does not know BOTW guest memory addresses.
Python 3.10+, Windows only. No keyboard/gamepad injection.
"""
import argparse
import json
import mmap
import socketserver
import struct
import sys
import threading
import time

MAGIC = 0x43594B53
VERSION = 11
NAME = "Local\\SkyCraft_v1"
COLLISION_RING = 0x20000
OVERLAY_PIXELS = COLLISION_RING + (32 << 20)
OVERLAY_SLOT_BYTES = 3840 * 2160 * 4
RENDER_RING = OVERLAY_PIXELS + 3 * OVERLAY_SLOT_BYTES
MAPPING_BYTES = RENDER_RING + (64 << 20)
OFF_HOST_STATE = 0x100
OFF_MC_STATE = 0x200
MAX_MESSAGE = 4096

class Bridge:
    def __init__(self, mapping_name=NAME):
        self.mapping = mmap.mmap(-1, MAPPING_BYTES, tagname=mapping_name,
                                 access=mmap.ACCESS_WRITE)
        self.lock = threading.Lock()
        self.seq = 0
        self.last_packet = 0.0
        self.frame = 0
        # This mapping has the same binary offsets as the SkyCraft v11 protocol.
        # Fabric currently expects the Skyrim host heartbeat in this header.
        struct.pack_into("<IIIIQQ", self.mapping, 0, MAGIC, VERSION, 0, 0, 0, 0)
        self.mapping[OFF_HOST_STATE:OFF_HOST_STATE + 0x40] = bytes(0x40)

    def update(self, data):
        if not isinstance(data, dict) or data.get("type") != "pose":
            raise ValueError("expected pose object")
        for k in ("x", "y", "z", "yaw", "pitch"):
            if not isinstance(data.get(k), (int, float)):
                raise ValueError("missing numeric field " + k)
        import math
        if not all(math.isfinite(data[k]) for k in ("x","y","z","yaw","pitch")):
            raise ValueError("nonfinite coordinate")
        if not isinstance(data.get("world", 1), int):
            raise ValueError("world must be integer")
        with self.lock:
            self.seq += 2
            # SkyState seqlock: odd while writing, then stable even.
            struct.pack_into("<I", self.mapping, OFF_HOST_STATE, self.seq - 1)
            # flags, worldId, collisionEpoch, pos XYZ, yaw, pitch,
            # teleportSeq, viewportW/H, gameHour.
            struct.pack_into("<III3d2fIIIf", self.mapping,
                             OFF_HOST_STATE + 4,
                             1, data.get("world", 1) & 0xffffffff, 0,
                             float(data["x"]), float(data["y"]), float(data["z"]),
                             float(data["yaw"]), float(data["pitch"]),
                             0, 1280, 720, 12.0)
            struct.pack_into("<I", self.mapping, OFF_HOST_STATE, self.seq)
            self.last_packet = time.monotonic()

    def minecraft_status(self):
        with self.lock:
            try:
                seq, flags = struct.unpack_from("<II", self.mapping, OFF_MC_STATE)
                x, y, z = struct.unpack_from("<3d", self.mapping, OFF_MC_STATE + 8)
                return dict(seq=seq, flags=flags, x=x, y=y, z=z)
            except (ValueError, struct.error):
                return dict(error="invalid Minecraft state")

    def heartbeat(self):
        # No false in-game flag: stale guest feed marks host inactive.
        with self.lock:
            alive = time.monotonic() - self.last_packet < 1.0
            flags = 1 if alive else 0
            struct.pack_into("<I", self.mapping, OFF_HOST_STATE + 4, flags)
            struct.pack_into("<Q", self.mapping, 16, int(time.monotonic()*1000))
            return alive

class Client(socketserver.StreamRequestHandler):
    def handle(self):
        if self.client_address[0] != "127.0.0.1":
            return
        while True:
            raw = self.rfile.readline(MAX_MESSAGE + 1)
            if not raw:
                return
            if len(raw) > MAX_MESSAGE or not raw.endswith(b"\n"):
                self.wfile.write(b'{"error":"oversized message"}\n')
                return
            try:
                value = json.loads(raw)
                self.server.bridge.update(value)
                reply = {"ok": True, "minecraft": self.server.bridge.minecraft_status()}
            except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as e:
                reply = {"error": str(e)}
            self.wfile.write((json.dumps(reply) + "\n").encode())

class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=39847)
    parser.add_argument("--mapping", default=NAME)
    args = parser.parse_args()
    if sys.platform != "win32":
        raise SystemExit("This host bridge requires Windows named mappings")
    bridge = Bridge(args.mapping)
    with Server(("127.0.0.1", args.port), Client) as server:
        server.bridge = bridge
        threading.Thread(target=server.serve_forever, daemon=True).start()
        print(f"BotwCraft host bridge running on 127.0.0.1:{args.port}; Ctrl+C to quit")
        print("Waiting for a real BOTW guest adapter. No game state is faked.")
        try:
            while True:
                bridge.heartbeat()
                time.sleep(.05)
        except KeyboardInterrupt:
            pass
        finally:
            server.shutdown()
            bridge.mapping.close()

if __name__ == "__main__":
    main()
