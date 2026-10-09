"""BOTW -> Minecraft SkyCraft v11 shared-memory bridge.

Accepts measured game poses over localhost. No synthetic gameplay state and no
guest pointer reads. The bridge also reads the Minecraft -> game state, but a
game-side receiver is still required to apply movement in BOTW.
"""
import argparse
import ctypes
import json
import math
import mmap
import os
import socketserver
import struct
import sys
import threading
import time

MAGIC = 0x43594B53
VERSION = 11
NAME = "Local\\SkyCraft_v1"
OFF_SKY_STATE = 0x100
OFF_MC_STATE = 0x200
OFF_COLLISION_RING = 0x20000
OFF_OVERLAY_PIXELS = OFF_COLLISION_RING + (32 << 20)
OVERLAY_SLOT_BYTES = 3840 * 2160 * 4
OFF_RENDER_RING = OFF_OVERLAY_PIXELS + 3 * OVERLAY_SLOT_BYTES
MAPPING_BYTES = OFF_RENDER_RING + (64 << 20)
MAX_MESSAGE = 4096
OFF_INPUT_RING = 0x1000
IR_HEAD = 0x00
IR_TAIL = 0x40
IR_DATA = 0x80
INPUT_RING_ENTRIES = 4096
INPUT_EVENT = struct.Struct("<HHiii")  # exact SkyCraft v11 InputEvent, 16 bytes
MC_IN_WORLD = 1
STATE_PACK = struct.Struct("<III3d2fIIIf")  # SkyState beyond seq = 60 bytes
assert STATE_PACK.size == 60
assert struct.calcsize("<IIIIQQ") == 0x20

def uptime_ms():
    """Same clock as SkyCraft Fabric's GetTickCount64() heartbeat."""
    if sys.platform == "win32":
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.GetTickCount64.restype = ctypes.c_ulonglong
        return kernel32.GetTickCount64()
    return int(time.monotonic() * 1000)  # portable unit tests only

def _real(value):
    return type(value) in (float, int) and math.isfinite(value) and abs(value) < 1e6

class Bridge:
    def __init__(self, mapping_name=NAME, memory=None, clock=uptime_ms, preview_blocks=False):
        if memory is None:
            if sys.platform != "win32":
                raise OSError("Windows named mappings are required")
            memory = mmap.mmap(-1, MAPPING_BYTES, tagname=mapping_name, access=mmap.ACCESS_WRITE)
        if len(memory) < OFF_MC_STATE + 0x100:
            raise ValueError("memory mapping too short")
        self.mapping = memory
        self.clock = clock
        self.preview_blocks = preview_blocks
        self.lock = threading.RLock()
        self.seq = 0
        self.last_packet = None
        self.last_world = None
        self.teleport_seq = 0
        struct.pack_into("<IIIIQQ", memory, 0, MAGIC, VERSION, os.getpid(), 0, 0, 0)
        memory[OFF_SKY_STATE:OFF_SKY_STATE + 0x40] = bytes(0x40)

    def update(self, data):
        if not isinstance(data, dict) or data.get("type") != "pose":
            raise ValueError("expected pose object")
        if not all(_real(data.get(k)) for k in ("x", "y", "z", "yaw", "pitch")):
            raise ValueError("pose requires finite numeric x/y/z/yaw/pitch")
        world = data.get("world", 1)
        if type(world) is not int or not (0 <= world <= 0xFFFFFFFF):
            raise ValueError("world must be an unsigned 32-bit integer")
        with self.lock:
            if world != self.last_world:
                self.teleport_seq = (self.teleport_seq + 1) & 0xFFFFFFFF
                self.last_world = world
            self.seq += 2
            struct.pack_into("<I", self.mapping, OFF_SKY_STATE, self.seq - 1)
            STATE_PACK.pack_into(
                self.mapping, OFF_SKY_STATE + 4,
                1, world, self.teleport_seq,  # in-game flag, world, collision epoch
                float(data["x"]), float(data["y"]), float(data["z"]),
                float(data["yaw"]), float(data["pitch"]),
                self.teleport_seq, 1280, 720, 12.0,
            )
            struct.pack_into("<I", self.mapping, OFF_SKY_STATE, self.seq)
            self.last_packet = self.clock()
            struct.pack_into("<Q", self.mapping, 16, self.last_packet)

    def minecraft_status(self):
        with self.lock:
            for _ in range(4):
                first = struct.unpack_from("<I", self.mapping, OFF_MC_STATE)[0]
                if first & 1:
                    continue
                flags = struct.unpack_from("<I", self.mapping, OFF_MC_STATE + 4)[0]
                xyz = struct.unpack_from("<3d", self.mapping, OFF_MC_STATE + 8)
                yaw, pitch = struct.unpack_from("<2f", self.mapping, OFF_MC_STATE + 0x20)
                frame = struct.unpack_from("<Q", self.mapping, OFF_MC_STATE + 0x38)[0]
                second = struct.unpack_from("<I", self.mapping, OFF_MC_STATE)[0]
                if first == second:
                    return dict(seq=second, flags=flags, in_world=bool(flags & MC_IN_WORLD),
                                x=xyz[0], y=xyz[1], z=xyz[2], yaw=yaw, pitch=pitch,
                                frame=frame)
            return dict(error="Minecraft state was being updated")

    def push_inputs(self, events):
        """Push input events into the exact SkyCraft v11 16-byte input ring.

        Events are sequences [kind, SDL_scancode_or_button, a, b, c].
        The Java consumer owns IR_TAIL; this producer publishes IR_HEAD last.
        """
        if not isinstance(events, list) or len(events) > 64:
            raise ValueError("events must be a list of at most 64 events")
        if len(self.mapping) < OFF_INPUT_RING + IR_DATA + INPUT_RING_ENTRIES * INPUT_EVENT.size:
            raise ValueError("mapping too short for input ring")
        validated = []
        for event in events:
            if (not isinstance(event, (list, tuple)) or len(event) != 5 or
                any(type(value) is not int for value in event)):
                raise ValueError("each input event must have five integers")
            kind, code, a, b, c = event
            if not (1 <= kind <= 6 and 0 <= code <= 65535 and
                    all(-(2 ** 31) <= v < 2 ** 31 for v in (a, b, c))):
                raise ValueError("invalid SkyCraft input event")
            validated.append(event)
        with self.lock:
            head = struct.unpack_from("<Q", self.mapping, OFF_INPUT_RING + IR_HEAD)[0]
            tail = struct.unpack_from("<Q", self.mapping, OFF_INPUT_RING + IR_TAIL)[0]
            # Never overwrite unread input: drop instead of losing key-up state.
            if tail > head or head - tail + len(validated) > INPUT_RING_ENTRIES:
                raise ValueError("SkyCraft input ring full or inconsistent")
            for event in validated:
                offset = OFF_INPUT_RING + IR_DATA + (head & (INPUT_RING_ENTRIES - 1)) * INPUT_EVENT.size
                INPUT_EVENT.pack_into(self.mapping, offset, *event)
                head += 1
            struct.pack_into("<Q", self.mapping, OFF_INPUT_RING + IR_HEAD, head)
            return len(validated)

    def heartbeat(self):
        with self.lock:
            if self.preview_blocks:
                # PREVIEW ONLY: this is a self-contained MC creative playground,
                # NOT Link's BOTW pose, no game collision or camera matching.
                mc = self.minecraft_status()
                in_world = mc.get("in_world", False)
                use_mc = in_world and all(
                    _real(mc.get(k)) for k in ("x", "y", "z", "yaw", "pitch")
                )
                self.update(dict(
                    type="pose",
                    x=mc["x"] if use_mc else 0.0,
                    y=mc["y"] if use_mc else 80.0,
                    z=mc["z"] if use_mc else 0.0,
                    yaw=mc["yaw"] if use_mc else 0.0,
                    pitch=mc["pitch"] if use_mc else 0.0,
                    world=1,
                ))
            now = self.clock()
            alive = self.last_packet is not None and 0 <= now - self.last_packet < 1000
            # Do NOT signal a live game when there is no fresh valid game pose.
            struct.pack_into("<Q", self.mapping, 16, now if alive else 0)
            struct.pack_into("<I", self.mapping, OFF_SKY_STATE + 4, 1 if alive else 0)
            return alive

    def close(self):
        if hasattr(self.mapping, "close"):
            self.mapping.close()

class Client(socketserver.StreamRequestHandler):
    def handle(self):
        if self.client_address[0] != "127.0.0.1":
            return
        while True:
            raw = self.rfile.readline(MAX_MESSAGE + 1)
            if not raw:
                break
            if len(raw) > MAX_MESSAGE or not raw.endswith(b"\n"):
                self.wfile.write(b'{"error":"invalid message size"}\n')
                break
            try:
                data = json.loads(raw)
                if not isinstance(data, dict):
                    raise ValueError("expected JSON object")
                kind = data.get("type")
                if kind == "pose":
                    self.server.bridge.update(data)
                    reply = {"ok": True, "minecraft": self.server.bridge.minecraft_status()}
                elif kind == "input":
                    count = self.server.bridge.push_inputs(data.get("events"))
                    reply = {"ok": True, "queued": count}
                elif kind == "minecraft":
                    reply = {"ok": True, "minecraft": self.server.bridge.minecraft_status()}
                else:
                    raise ValueError("unknown bridge message type")
            except (TypeError, ValueError, json.JSONDecodeError) as exc:
                reply = {"error": str(exc)}
            self.wfile.write((json.dumps(reply) + "\n").encode("utf-8"))

class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=39847)
    parser.add_argument("--mapping", default=NAME)
    parser.add_argument("--preview-blocks", action="store_true",
                        help="Self-contained experimental Minecraft blocks sandbox (NOT BOTW player sync)")
    args = parser.parse_args()
    if sys.platform != "win32":
        raise SystemExit("Run the bridge on Windows (Ryujinx PC)")
    bridge = Bridge(mapping_name=args.mapping, preview_blocks=args.preview_blocks)
    if args.preview_blocks:
        print("[BotwCraft] EXPERIMENTAL BLOCKS: synthetic preview world, "
              "no BOTW terrain/Link tracking", flush=True)
    try:
        with Server(("127.0.0.1", args.port), Client) as server:
            server.bridge = bridge
            threading.Thread(target=server.serve_forever, daemon=True).start()
            print(f"[BotwCraft] Bridge ready on 127.0.0.1:{args.port}; Ctrl+C to quit", flush=True)
            try:
                while True:
                    bridge.heartbeat()
                    time.sleep(0.05)
            except KeyboardInterrupt:
                pass
            finally:
                server.shutdown()
    finally:
        bridge.close()

if __name__ == "__main__":
    main()
