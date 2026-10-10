"""SkyCraft Fabric RenderRing -> Ryujinx virtual SD -> real BOTW NVN DrawMesh.

Unlike the abandoned desktop preview, this writes native geometry to the
WiiXLaunch game module's own SD directory. Geometry is drawn by Nintendo's
in-game NVN command buffer. An accurate Zelda camera/depth link is still a
separate unsolved problem; our temporary MC eye projection is not an accurate
Hyrule-world transform.
"""
from __future__ import annotations

import argparse
import ctypes
import math
import mmap
import os
from pathlib import Path
import struct
import sys
import tempfile
import time

MAPPING_NAME = "Local\\SkyCraft_v1"
PROTOCOL_MAGIC = 0x43594B53
PROTOCOL_VERSION = 11
OVERLAY_SLOT_BYTES = 3840 * 2160 * 4
OFF_RENDER_RING = 0x20000 + (32 << 20) + (3 * OVERLAY_SLOT_BYTES)
RENDER_RING_BYTES = 64 << 20
RENDER_RING_DATA = 0x80
RENDER_RING_CAPACITY = RENDER_RING_BYTES - RENDER_RING_DATA
MAPPING_BYTES = OFF_RENDER_RING + RENDER_RING_BYTES
OFF_MC_STATE = 0x200
RENDER_SECTION = 2
RENDER_CLEAR_ALL = 3
RENDER_PAD = 0
RENDER_VERTEX_BYTES = 32
MESH_MAGIC = 0x31435742
MESH_VERSION = 1
MAX_VERTICES = 510     # divides by 3; native guest allows 512
HEADER = struct.Struct("<8I")              # 32 bytes
SECTION = struct.Struct("<iiiI")            # 16 bytes
RENDER_VERTEX = struct.Struct("<5f3I")     # 32 bytes
NATIVE_VERTEX = struct.Struct("<8f")       # 32 bytes
DEFAULT_RELATIVE_PATH = Path(
    "WiiXLaunch/mods/01007EF00011E000/botwcraft/frame.bin"
)
# Title-specific mod ROMFS used by WiiXLaunch's own guest loader.
# Ryujinx may snapshot this at launch; host writes are experimental.
ROMFS_RELATIVE_PATH = Path(
    "mods/contents/01007ef00011e000/BotwCraft/"
    "romfs/WiiXLaunch/mods/botwcraft/frame.bin"
)

def fnv1a(data: bytes) -> int:
    result = 2166136261
    for value in data:
        result = ((result ^ value) * 16777619) & 0xffffffff
    return result

def encode_mesh(frame: int, vertices: list[tuple[float, ...]]) -> bytes:
    if type(frame) is not int or not (0 <= frame <= 0xffffffff):
        raise ValueError("invalid frame")
    if len(vertices) > MAX_VERTICES or len(vertices) % 3:
        raise ValueError("invalid triangle vertex count")
    payload = bytearray()
    for values in vertices:
        if len(values) != 8 or not all(
                isinstance(v, (int, float)) and math.isfinite(v) for v in values):
            raise ValueError("invalid projected vertex")
        x, y, z, w = values[:4]
        if not (-10000 < x < 10000 and -10000 < y < 10000 and
                -10000 < z < 10000 and 0 < w <= 1000):
            raise ValueError("invalid native clip coordinates")
        payload.extend(NATIVE_VERTEX.pack(*values))
    head = HEADER.pack(
        MESH_MAGIC, MESH_VERSION, frame, len(vertices), fnv1a(payload), 0, 0, 0)
    return head + payload

def decode_render_ring(shared, max_events=256):
    """Consume exact SkyCraft v11 ring, never reading past its wrap boundary.

    Return (events, consumed_messages). Head written by Java, tail by us.
    Both are monotonic u64 counters. In a normal deployment, no Skyrim
    consumer is competing for this ring.
    """
    off = OFF_RENDER_RING
    head = struct.unpack_from("<Q", shared, off)[0]
    tail = struct.unpack_from("<Q", shared, off + 0x40)[0]
    if head < tail or head - tail > RENDER_RING_CAPACITY:
        # An old reader/writer left a corrupt or overwritten ring: resync.
        struct.pack_into("<Q", shared, off + 0x40, head)
        return [], 0
    events = []
    consumed = 0
    while tail < head and consumed < max_events:
        pos = int(tail % RENDER_RING_CAPACITY)
        remaining = RENDER_RING_CAPACITY - pos
        if remaining < 8:
            tail += remaining
            continue
        location = off + RENDER_RING_DATA + pos
        kind, length = struct.unpack_from("<II", shared, location)
        if kind == RENDER_PAD:
            tail += remaining
            consumed += 1
            continue
        total = (8 + length + 7) & ~7
        if length > RENDER_RING_CAPACITY - 8 or total > remaining or tail + total > head:
            # Never walk a partially written or malformed message.
            break
        if kind == RENDER_CLEAR_ALL:
            events.append(("clear", None))
        elif kind == RENDER_SECTION:
            if length >= SECTION.size:
                sx, sy, sz, count = SECTION.unpack_from(shared, location + 8)
                if (count <= 100_000 and count % 3 == 0 and
                    length == SECTION.size + count * RENDER_VERTEX_BYTES and
                    all(-100_000 < v < 100_000 for v in (sx, sy, sz))):
                    payload = bytes(shared[
                        location + 8 + SECTION.size:
                        location + 8 + SECTION.size + count * RENDER_VERTEX_BYTES])
                    events.append(("section", (sx, sy, sz, count, payload)))
        tail += total
        consumed += 1
    struct.pack_into("<Q", shared, off + 0x40, tail)
    return events, consumed

def read_minecraft_pose(shared):
    """Read Minecraft's own physics pose (not a fabricated Link position)."""
    first = struct.unpack_from("<I", shared, OFF_MC_STATE)[0]
    if first & 1:
        return None
    flags = struct.unpack_from("<I", shared, OFF_MC_STATE + 4)[0]
    pos = struct.unpack_from("<3d", shared, OFF_MC_STATE + 8)
    yaw, pitch = struct.unpack_from("<2f", shared, OFF_MC_STATE + 0x20)
    second = struct.unpack_from("<I", shared, OFF_MC_STATE)[0]
    if first != second or not (flags & 1):
        return None
    if not all(math.isfinite(v) and abs(v) < 100_000 for v in (*pos, yaw, pitch)):
        return None
    return (*pos, yaw, pitch)

def project(world, camera, fov_degrees=70, aspect=16/9):
    """Use Minecraft camera for early projection, not Zelda camera matrices."""
    dx, dy, dz = world[0]-camera[0], world[1]-(camera[1]+1.62), world[2]-camera[2]
    yaw, pitch = math.radians(camera[3]), math.radians(camera[4])
    c, s = math.cos(yaw), math.sin(yaw)
    right = dx*c + dz*s
    forward = -dx*s + dz*c
    depth = forward * math.cos(pitch) - dy * math.sin(pitch)
    up = forward * math.sin(pitch) + dy * math.cos(pitch)
    if depth < 0.15 or depth > 140:
        return None
    scale = math.tan(math.radians(fov_degrees) * .5)
    x = right / (depth * scale * aspect)
    y = up / (depth * scale)
    if not all(math.isfinite(v) for v in (x, y)):
        return None
    return (x, y, .5, 1.0)

def sections_to_mesh(sections, camera, max_vertices=MAX_VERTICES):
    """Project real Minecraft section triangles into the native NVN format."""
    triangles = []
    for sx, sy, sz, count, data in sections.values():
        for i in range(0, count, 3):
            tri = []
            for j in range(3):
                x, y, z, u, v, color, light, flags = RENDER_VERTEX.unpack_from(
                    data, (i+j) * RENDER_VERTEX_BYTES)
                if not all(math.isfinite(n) for n in (x, y, z)):
                    tri = []
                    break
                pos = project((sx*16+x, sy*16+y, sz*16+z), camera)
                if pos is None:
                    tri = []
                    break
                nx = -1.0 if flags & (1<<4) else 1.0
                tri.append((*pos, nx, 0.6, 0.5, 1.0))
            if len(tri) == 3:
                triangles.extend(tri)
                if len(triangles) >= max_vertices:
                    return triangles
    return triangles

def minecraft_heartbeat_is_live(shared, now_ms, max_age_ms=3500):
    """Refuse to keep rendering ghost blocks from a disconnected MC instance."""
    mc_stamp = struct.unpack_from("<Q", shared, 0x18)[0]
    return mc_stamp > 0 and 0 <= now_ms - mc_stamp <= max_age_ms

def write_atomic(path: Path, content: bytes, retries=3, sleeper=time.sleep):
    """Publish a complete mesh via a unique temp file in the SAME directory.

    The legacy fixed filename frame.bin.part could be left behind, made a
    directory, or held open by another process. A unique tempfile avoids
    collisions with prior attempts and concurrent bridge launches.
    Windows may temporarily deny os.replace while a reader has an open
    handle; retry boundedly, never modify permissions or kill the reader.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        fd, name = tempfile.mkstemp(prefix=path.name + ".", suffix=".part",
                                   dir=str(path.parent))
        temporary = Path(name)
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
        for attempt in range(retries + 1):
            try:
                os.replace(temporary, path)
                temporary = None
                return
            except PermissionError:
                if attempt == retries:
                    raise
                sleeper(min(.06 * (2 ** attempt), .30))
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass


def describe_write_failure(path: Path, exc: OSError) -> str:
    """Report relevant clues, without guessing which Windows ACL denied access."""
    legacy = path.with_name(path.name + ".part")
    clues = [f"{type(exc).__name__}: {exc}"]
    if legacy.is_dir():
        clues.append(f"old fixed-name temporary path is a DIRECTORY: {legacy}")
    elif legacy.exists():
        clues.append(f"old fixed-name temporary path remains: {legacy}")
    if path.is_dir():
        clues.append(f"destination is a DIRECTORY, not a file: {path}")
    if not path.parent.is_dir():
        clues.append(f"destination parent unavailable: {path.parent}")
    clues.append("Avoid running the bridge as administrator. Close Ryujinx and "
                 "other bridge processes and inspect the destination folder ACLs.")
    return " | ".join(clues)


class RecoverableMeshWriter:
    """An unavailable Ryujinx SD must never terminate the Link telemetry relay."""

    def __init__(self, destination, writer=write_atomic, printer=print,
                 clock=time.monotonic, report_every=20.0):
        self.destination = Path(destination)
        self.writer = writer
        self.printer = printer
        self.clock = clock
        self.report_every = report_every
        self.failures = 0
        self.last_report = None

    def write(self, packet) -> bool:
        try:
            self.writer(self.destination, packet)
        except OSError as exc:
            self.failures += 1
            now = self.clock()
            if self.last_report is None or now - self.last_report >= self.report_every:
                self.last_report = now
                self.printer("[BotwCraft] WARNING: native mesh output unavailable; "
                             "Link telemetry and Minecraft bridge continue. "
                             + describe_write_failure(self.destination, exc),
                             flush=True)
            return False
        if self.failures:
            self.printer("[BotwCraft] Native mesh output is writable again: "
                         + str(self.destination), flush=True)
            self.failures = 0
            self.last_report = None
        return True


def resolve_sd_root(override=None):
    if override or os.environ.get("BOTWCRAFT_SDROOT"):
        folder = Path(override or os.environ["BOTWCRAFT_SDROOT"]).expanduser()
    else:
        appdata = os.environ.get("APPDATA")
        if not appdata:
            raise RuntimeError("APPDATA unavailable, supply --sd-root")
        folder = Path(appdata) / "Ryujinx" / "sdcard"
    if not folder.is_dir():
        raise FileNotFoundError(f"Ryujinx SD card not found: {folder}. Use --sd-root.")
    return folder

def resolve_romfs_output(sd_root):
    """Only use the ROMFS destination if our installer already seeded it.

    Do not create unrequested mod directories or overwrite third-party mods.
    This path is an EXPERIMENTAL channel: many Ryujinx versions construct a
    ROMFS snapshot at game startup so replacing a file later is not live.
    """
    path = Path(sd_root).parent / ROMFS_RELATIVE_PATH
    return path if path.is_file() else None


def run(sd_root, hz=8):
    """Diagnose Minecraft SkyCraft v11 render packets without touching Ryujinx.

    The guest ROMFS reader caused a verified Ryujinx crash, and the Switch SD
    mount is rejected. Until there is a supported live host->guest channel,
    writing frame.bin is neither productive nor safe.
    """
    if sys.platform != "win32":
        raise RuntimeError("Windows host required")
    print("[BotwCraft] Native mesh DIAGNOSTICS ONLY: no SD/ROMFS file writes,",
          flush=True)
    print("[BotwCraft] Nintendo Switch mesh renderer is disabled after the",
          "Ryujinx nn::fs::ReadFile crash. Link telemetry remains active.",
          flush=True)
    kernel = ctypes.windll.kernel32
    kernel.GetTickCount64.restype = ctypes.c_uint64
    memory = mmap.mmap(-1, MAPPING_BYTES, tagname=MAPPING_NAME)
    sections = {}
    report_count = 0
    last_valid_pose = False
    try:
        while True:
            magic, version = struct.unpack_from("<II", memory)
            if (magic, version) == (PROTOCOL_MAGIC, PROTOCOL_VERSION):
                events, _ = decode_render_ring(memory)
                for kind, data in events:
                    if kind == "clear":
                        sections.clear()
                    else:
                        section_key = data[:3]
                        if data[3] == 0:
                            sections.pop(section_key, None)
                        else:
                            sections[section_key] = data
                pose = (read_minecraft_pose(memory)
                        if minecraft_heartbeat_is_live(
                            memory, int(kernel.GetTickCount64())) else None)
                last_valid_pose = pose is not None
                if report_count % (hz * 10) == 0:
                    vertex_list = sections_to_mesh(sections, pose) if pose else []
                    print(
                        f"[BotwCraft] Minecraft export: {len(sections)} sections, "
                        f"{len(vertex_list)//3} projected triangles, "
                        f"pose={'present' if last_valid_pose else 'absent'}. "
                        "No native injection.",
                        flush=True)
                report_count += 1
            time.sleep(1/hz)
    except KeyboardInterrupt:
        pass
    finally:
        memory.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sd-root", help="Actual Ryujinx virtual sdcard folder")
    parser.add_argument("--hz", type=int, default=8)
    args = parser.parse_args()
    if not 1 <= args.hz <= 20:
        parser.error("--hz must be 1..20")
    try:
        run(args.sd_root, args.hz)
    except (OSError, RuntimeError) as exc:
        raise SystemExit(f"[BotwCraft] Native mesh bridge error: {exc}")

if __name__ == "__main__":
    main()
