"""Inspect the real SkyCraft v11 GPU HUD overlay frames, no Minecraft screenshots.

The original Minecraft FrameExporter publishes full RGBA frames into three
shared-memory slots. This diagnostic saves ONE frame as PNG to verify the
pixel stream *before* wiring it to WiiXLaunch's native NVN renderer.
"""
import argparse
import mmap
from pathlib import Path
import struct
import sys
import time
import zlib

try:
    from . import host_bridge as host
except ImportError:
    import host_bridge as host

OFF_OVERLAY_CTL=0x300
OFF_OVERLAY_SLOT_HDR=0x340
OVERLAY_DIRTY=4
SLOT_HDR_SIZE=0x40
SH_WIDTH=0
SH_HEIGHT=4
SH_FLAGS=8
SH_FRAME_ID=0x10
MAX_W=3840
MAX_H=2160


def read_latest(mapping):
    """Return (width,height,flipped,frame_id,rgba) or None if not published."""
    state=struct.unpack("<I",mapping[OFF_OVERLAY_CTL:OFF_OVERLAY_CTL+4])[0]
    if not state & OVERLAY_DIRTY:
        return None
    slot=state & 3
    if slot>2:
        return None
    hdr=OFF_OVERLAY_SLOT_HDR+slot*SLOT_HDR_SIZE
    width,height,flags=struct.unpack("<III",mapping[hdr:hdr+12])
    frame_id=struct.unpack("<Q",mapping[hdr+SH_FRAME_ID:hdr+SH_FRAME_ID+8])[0]
    if not (0<width<=MAX_W and 0<height<=MAX_H and frame_id>0):
        return None
    start=host.OFF_OVERLAY_PIXELS+slot*host.OVERLAY_SLOT_BYTES
    data=bytes(mapping[start:start+width*height*4])
    # This reader is deliberately read-only. If writer swapped slots while
    # sampling, discard rather than save an incomplete HUD.
    if struct.unpack("<I",mapping[OFF_OVERLAY_CTL:OFF_OVERLAY_CTL+4])[0]!=state:
        return None
    return width,height,bool(flags&1),frame_id,data


def make_png(width,height,bottom_up,rgba):
    if not (0<width<=MAX_W and 0<height<=MAX_H and len(rgba)==width*height*4):
        raise ValueError("invalid source image")
    stride=width*4
    rows=(rgba[i*stride:(i+1)*stride] for i in
          (range(height-1,-1,-1) if bottom_up else range(height)))
    raw=b"".join(b"\x00"+row for row in rows)
    def chunk(kind,payload):
        return (struct.pack(">I",len(payload))+kind+payload+
                struct.pack(">I",zlib.crc32(kind+payload)&0xffffffff))
    return (b"\x89PNG\r\n\x1a\n"+
            chunk(b"IHDR",struct.pack(">IIBBBBB",width,height,8,6,0,0,0))+
            chunk(b"IDAT",zlib.compress(raw,5))+chunk(b"IEND",b""))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out",type=Path,default=Path("minecraft-hud-test.png"))
    p.add_argument("--timeout",type=int,default=30)
    a=p.parse_args()
    if sys.platform!="win32":
        raise SystemExit("Windows SkyCraft named memory map required")
    previous=None
    start=time.monotonic()
    with mmap.mmap(-1,host.MAPPING_BYTES,tagname=host.NAME) as shared:
        print("[BotwCraft HUD] En attente du HUD réel Minecraft. "
              "Dans Minecraft: /botwcraft connect puis /botwcraft hud on",flush=True)
        while time.monotonic()-start<a.timeout:
            snap=read_latest(shared)
            if snap is not None and snap[3]!=previous:
                w,h,bottom,frame_id,pixels=snap
                a.out.write_bytes(make_png(w,h,bottom,pixels))
                print(f"[BotwCraft HUD] Capture originale reçue: {w}x{h}, "
                      f"frame {frame_id}, {a.out.resolve()}",flush=True)
                return
            time.sleep(0.1)
    raise SystemExit("[BotwCraft HUD] Aucune frame reçue. Vérifier le monde, "
                     "le bridge et /botwcraft hud on")


if __name__=="__main__":
    main()
