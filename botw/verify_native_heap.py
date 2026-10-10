"""Check WiiXLaunch .wxlm embeds the HUD arena request in its actual header.

WXLML v1 AArch64 header layout (WiiXLaunch scripts/wxlm.py):
  magic 0, formatVersion 4, machine 6, modId 12, heapRequest 108.
This deliberately checks COMPILED bytes, not just mod.json.
"""
from __future__ import annotations
import json
from pathlib import Path
import struct
import sys

MAGIC = 0x57584C4D
VERSION = 1
AARCH64 = 2
HEADER_BYTES = 144
OFFSET_HEAP_REQUEST = 108
MIN_HEAP = 52912 + 36896 + 32768


def verify(module: Path, manifest: Path):
    data = module.read_bytes()
    if len(data) < HEADER_BYTES:
        raise ValueError("wxlm file too short")
    magic, version, machine = struct.unpack_from("<IHH", data)
    if (magic, version, machine) != (MAGIC, VERSION, AARCH64):
        raise ValueError(f"wrong WiiXLaunch Switch module header: {magic:08x}/{version}/{machine}")
    mod_id = data[12:28].split(bytes((0,)),1)[0]
    if mod_id != b"botwcraft":
        raise ValueError("wrong module id")
    heap_request = struct.unpack_from("<I", data, OFFSET_HEAP_REQUEST)[0]
    declared = json.loads(manifest.read_text(encoding="utf-8"))["heapRequest"]
    if not (MIN_HEAP <= heap_request <= 512*1024):
        raise ValueError(f"compiled heapRequest={heap_request} B cannot fit BWH1 HUD; "
                         f"need at least {MIN_HEAP}")
    if declared != heap_request:
        raise ValueError(f"manifest requested {declared}, wxlm embeds {heap_request}")
    print(f"[BotwCraft] verified real .wxlm HUD heapRequest = {heap_request} bytes")
    return heap_request


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: python botw/verify_native_heap.py FILE.wxlm mod.json")
    verify(Path(sys.argv[1]), Path(sys.argv[2]))
