"""ONE-FRAME genuine Minecraft HUD -> native Zelda NVN texture proof.

No Win32 ghost overlay is opened. The Python process transports exactly one
128x72 image to our WiiXLaunch module's OWN heap using the local Ryujinx GDB
debugger. The guest invokes botw.gfx.CreateTexture and DrawSprite. Updating
the texture continuously requires WiiXLaunch's native texture update path
and is intentionally NOT implemented by repeatedly allocating textures.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import re
import struct
import sys
import time

try:
    from . import gdb_mesh_bridge as gdb
    from . import hud_overlay
except ImportError:
    import gdb_mesh_bridge as gdb
    import hud_overlay

MAGIC = 0x31485742  # BWH1
VERSION = 1
WIDTH = 128
HEIGHT = 72
HEADER = struct.Struct("<8I")
BYTES = WIDTH * HEIGHT * 4
CAPACITY = HEADER.size + BYTES
ANNOUNCE = re.compile(r"BotwCraft:NATIVE_HUD_BUFFER_ADDR=0x([0-9a-fA-F]{8,16})")


def hash_pixels(data):
    h = 2166136261
    for b in data:
        h = ((h ^ b) * 16777619) & 0xffffffff
    return h


def downsample_rgba(width, height, bottom_up, pixels):
    if not (1 <= width <= 3840 and 1 <= height <= 2160):
        raise ValueError("invalid Minecraft HUD dimensions")
    if len(pixels) != width * height * 4:
        raise ValueError("invalid original Minecraft HUD pixel length")
    output = bytearray(BYTES)
    for y in range(HEIGHT):
        ysrc = min(height - 1, (y * height) // HEIGHT)
        if bottom_up:
            ysrc = height - 1 - ysrc
        for x in range(WIDTH):
            xsrc = min(width - 1, (x * width) // WIDTH)
            start = (ysrc * width + xsrc) * 4
            dest = (y * WIDTH + x) * 4
            output[dest:dest+4] = pixels[start:start+4]
    return bytes(output)


def make_packet(frame):
    width, height, bottom_up, frame_id, pixels = frame
    pixels = downsample_rgba(width, height, bottom_up, pixels)
    header = HEADER.pack(MAGIC, VERSION, max(1, frame_id & 0xffffffff),
                         WIDTH, HEIGHT, BYTES, hash_pixels(pixels), 0)
    return header + pixels


def current_native_hud_mailbox(path):
    if path is None or not path.is_file():
        return None
    st = path.stat()
    if time.time() - st.st_mtime > 360:
        return None
    with path.open("rb") as handle:
        handle.seek(max(0, st.st_size - (8 << 20)))
        data = handle.read().decode("utf-8", errors="replace")
    builds = list(re.finditer(r"Game: build 0x[0-9a-fA-F]{8}", data))
    if not builds or builds[-1].group(0) != gdb.VERSION:
        return None
    current_game = data[builds[-1].start():]
    if "BotwCraft:NATIVE_HUD_CAPACITY=36896" not in current_game:
        return None
    addresses = ANNOUNCE.findall(current_game)
    if not addresses:
        return None
    pointer = int(addresses[-1], 16)
    return pointer if 0x10000 <= pointer < (1 << 48) else None


def hud_allocation_failure(path):
    """Return True only for the current BOTW boot's actual WiiXLaunch failure.

    Fail immediately instead of telling a user to reconnect Minecraft when
    a 64 KiB guest module cannot allocate the required 36,896-byte HUD.
    """
    if path is None or not path.is_file() or time.time() - path.stat().st_mtime > 360:
        return False
    with path.open("rb") as handle:
        handle.seek(max(0, path.stat().st_size - (8 << 20)))
        data = handle.read().decode("utf-8", errors="replace")
    builds = list(re.finditer(r"Game: build 0x[0-9a-fA-F]{8}", data))
    if not builds or builds[-1].group(0) != gdb.VERSION:
        return False
    boot = data[builds[-1].start():]
    return "BotwCraft:NATIVE_HUD_BUFFER_ALLOC_FAILED" in boot


def run(port=22225, log=None):
    if sys.platform != "win32":
        raise RuntimeError("Windows/Ryujinx required")
    print("[BotwCraft NVN HUD] Real in-game NVN texture test, NOT Win32 overlay.")
    print("[BotwCraft NVN HUD] ONE Minecraft HUD frame only, reduced to 128x72.")
    print("[BotwCraft NVN HUD] Start Minecraft HUD capture: "
          "/botwcraft connect, then /botwcraft hud on")
    ptr = None
    for i in range(90):
        src = gdb.log_source(log)
        ptr = current_native_hud_mailbox(src)
        if hud_allocation_failure(src):
            raise RuntimeError(
                "WiiXLaunch a refuse 36896 octets pour le HUD : ancien module "
                "64 Ko. Installe le .wxlm avec heapRequest=131072 de ce "
                "nouveau paquet, puis REDEMARRE Zelda entierement. "
                "Minecraft et le port GDB ne sont pas la cause.")
        if ptr:
            print(f"[BotwCraft NVN HUD] Guest memory at 0x{ptr:x}", flush=True)
            break
        if i % 5 == 0:
            print(f"[BotwCraft NVN HUD] Waiting for actual BOTW 1.5.0 "
                  f"guest HUD mailbox. Log: {src}", flush=True)
        time.sleep(2)
    if not ptr:
        raise RuntimeError("Native HUD mailbox missing: install the NEW "
                           "BotwCraft WiiXLaunch mod and use current Ryujinx log")

    shm = None
    try:
        start = time.monotonic()
        while time.monotonic() - start < 90:
            try:
                if shm is None:
                    shm = hud_overlay.SharedOverlay()
            except OSError:
                time.sleep(1)
                continue
            frame = shm.frame()
            if frame is not None:
                packet = make_packet(frame)
                assert len(packet) == CAPACITY
                print("[BotwCraft NVN HUD] GDB transfer of ONE real HUD frame"
                      f" ({len(packet)} bytes)...", flush=True)
                with gdb.RspClient(port=port) as debugger:
                    debugger.stop(first=True)
                    try:
                        debugger.write_memory(ptr, packet, max_packet=CAPACITY)
                    finally:
                        debugger.resume()
                print("[BotwCraft NVN HUD] Sent. Watch Ryujinx native log for "
                      "'BotwCraft:NATIVE_HUD_TEXTURE_CREATED'. "
                      "The image should appear IN Zelda, but remain STATIC.",flush=True)
                return
            time.sleep(0.25)
        raise RuntimeError("Minecraft has not published a HUD image")
    finally:
        if shm is not None:
            shm.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port",type=int,default=22225)
    parser.add_argument("--log",type=Path)
    args=parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("invalid GDB port")
    try:
        run(args.port,args.log)
    except KeyboardInterrupt:
        print("[BotwCraft NVN HUD] Cancelled safely.")
    except (OSError,RuntimeError,gdb.RspError,ValueError) as e:
        raise SystemExit("[BotwCraft NVN HUD] ERROR: " + str(e))


if __name__ == "__main__":
    main()
