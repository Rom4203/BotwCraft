"""Transport real SkyCraft 3D block meshes into WiiXLaunch's BWC2 world mailbox.

Unlike gdb_mesh_bridge.py this NEVER projects with Minecraft camera.
Link's observed world pose anchors Minecraft coordinates to Hyrule once.
Actual on-screen rendering waits for a native BOTW view/depth integration.
"""
from __future__ import annotations
import argparse
import ctypes
import mmap
import re
import struct
import sys
import time

try:
    from . import gdb_mesh_bridge as gdb
    from . import native_mesh_bridge as sharedmesh
    from . import world_space as world
except ImportError:
    import gdb_mesh_bridge as gdb
    import native_mesh_bridge as sharedmesh
    import world_space as world

WORLD_ADDR = re.compile(r"BotwCraft:BWC2_WORLD_BUFFER_ADDR=0x([0-9a-fA-F]{8,16})")
OFF_SKY_STATE = 0x100
H_SKY_HEARTBEAT = 0x10


def latest_world_mailbox(path):
    """Accept BWC2 mailbox addresses only from the current game version."""
    if path is None or not path.is_file():
        return None
    if time.time() - path.stat().st_mtime > 360:
        return None
    with path.open("rb") as fd:
        fd.seek(max(0, path.stat().st_size - (8<<20)))
        data = fd.read().decode("utf-8", errors="replace")
    versions = list(re.finditer(r"Game: build 0x[0-9A-Fa-f]{8}", data))
    if not versions or versions[-1].group() != gdb.VERSION:
        return None
    text = data[versions[-1].start():]
    if "BotwCraft:BWC2_WORLD_BUFFER_CAPACITY=15416" not in text:
        return None
    match = WORLD_ADDR.findall(text)
    if not match:
        return None
    result = int(match[-1],16)
    return result if 0x10000 <= result < (1<<48) else None


def link_world_position(shared):
    """SkyCraft v11 seqlock: reject uninitialized, menu or stale poses."""
    seq1 = struct.unpack_from("<I", shared, OFF_SKY_STATE)[0]
    if seq1 & 1:
        return None
    flags = struct.unpack_from("<I", shared, OFF_SKY_STATE + 4)[0]
    position = struct.unpack_from("<3d", shared, OFF_SKY_STATE + 0x10)
    seq2 = struct.unpack_from("<I", shared, OFF_SKY_STATE)[0]
    if seq1 != seq2 or not flags & 1:
        return None
    if not all(-100000 < f < 100000 for f in position):
        return None
    if position == (0.,0.,0.):
        return None
    return position


def run(args):
    if sys.platform != "win32":
        raise RuntimeError("Requires Ryujinx/Windows")
    guest_log = gdb.log_source(args.log)
    print("[BotwCraft World] Starting 3D world-space producer. "
          "No screen-coordinate projection or synthetic camera.", flush=True)
    print("[BotwCraft World] Zelda log:", guest_log, flush=True)
    kernel = ctypes.windll.kernel32
    kernel.GetTickCount64.restype=ctypes.c_uint64
    with mmap.mmap(-1, sharedmesh.MAPPING_BYTES,
                   tagname=sharedmesh.MAPPING_NAME) as shared:
        while True:
            source = gdb.log_source(args.log)
            pointer = latest_world_mailbox(source)
            if pointer is not None:
                break
            print("[BotwCraft World] Waiting for BOTW 1.5.0 BWC2 mailbox...",
                  flush=True)
            time.sleep(3)
        print(f"[BotwCraft World] Hyrule world-scene buffer: 0x{pointer:x}",
              flush=True)
        print("[BotwCraft World] Geometries are 3D; a native Zelda camera "
              "and depth hookup is required to make them visible.", flush=True)
        sections = {}
        fixed_anchor = None
        sequence = 1
        printed = 0.0
        last_sent = 0.0
        with gdb.RspClient(port=args.port) as debugger:
            debugger.stop(first=True)
            debugger.resume()
            while True:
                if struct.unpack_from("<II", shared) != (
                        sharedmesh.PROTOCOL_MAGIC,
                        sharedmesh.PROTOCOL_VERSION):
                    time.sleep(.1)
                    continue
                events, _ = sharedmesh.decode_render_ring(shared)
                for kind, data in events:
                    if kind == "clear":
                        sections.clear()
                    elif data[3] == 0:
                        sections.pop(data[:3],None)
                    else:
                        sections[data[:3]] = data
                mc = (sharedmesh.read_minecraft_pose(shared)
                      if sharedmesh.minecraft_heartbeat_is_live(
                          shared, int(kernel.GetTickCount64()))
                      else None)
                link = link_world_position(shared)
                if fixed_anchor is None and mc is not None and link is not None:
                    fixed_anchor = world.WorldAnchor(mc[:3],link)
                    print("[BotwCraft World] Fixed world alignment: "
                          f"MC={fixed_anchor.mc} <-> Hyrule={fixed_anchor.botw}",
                          flush=True)
                now = time.monotonic()
                if fixed_anchor and sections and now-last_sent >= 1/args.hz:
                    vertices = world.world_vertices(sections,fixed_anchor)
                    if vertices:
                        packet = world.pack(sequence,fixed_anchor,vertices)
                        debugger.stop()
                        try:
                            debugger.write_memory(pointer,packet)
                        finally:
                            debugger.resume()
                        sequence = (sequence + 1) & 0xffffffff
                        last_sent = now
                        if now-printed >= 4:
                            print(f"[BotwCraft World] {len(sections)} sections, "
                                  f"{len(vertices)//3} WORLD-SPACE triangles "
                                  f"sent ({len(packet)} bytes).",flush=True)
                            printed = now
                time.sleep(.025)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--port",type=int,default=22225)
    p.add_argument("--log",type=str,default=None)
    p.add_argument("--hz",type=float,default=1.0)
    a=p.parse_args()
    if not 1<=a.port<=65535 or not .2<=a.hz<=2:
        p.error("port 1..65535, hz 0.2..2")
    try:
        run(a)
    except KeyboardInterrupt:
        print("[BotwCraft World] Stopped.")
    except (OSError,RuntimeError,ValueError,gdb.RspError) as e:
        raise SystemExit(f"[BotwCraft World] ERROR: {e}")


if __name__=="__main__":
    main()
