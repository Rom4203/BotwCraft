"""SkyCraft-compatible 3D block geometry, without screen-space projection.

This is the *world* channel, distinct from the old BWC1 2D NVN GPU probe.
Vertices preserve actual block positions, atlas UVs, lighting and tint.
An origin pair fixes Minecraft's coordinate system to Hyrule at connection.
Zelda camera/depth and Havok collision are independent guest-side consumers.
"""
from __future__ import annotations
from dataclasses import dataclass
import math
import struct

from . import native_mesh_bridge as legacy

MAGIC = 0x32435742  # BWC2
VERSION = 2
HEADER = struct.Struct("<8I6f")  # 56 bytes
VERTEX = struct.Struct("<5f3I")  # 32 bytes, byte-for-byte SkyCraft RenVertex
MAX_VERTICES = 480  # whole triangles and <= 16 KiB guest mailbox
SCALE = 1.0


@dataclass(frozen=True)
class WorldAnchor:
    mc: tuple[float, float, float]
    botw: tuple[float, float, float]
    scale: float = SCALE

    def __post_init__(self):
        if not all(math.isfinite(x) and abs(x) < 100000 for x in (*self.mc, *self.botw)):
            raise ValueError("origin must be a finite world position")
        if not math.isfinite(self.scale) or not (0.001 <= self.scale <= 100):
            raise ValueError("invalid cross-game scale")

    def to_hyrule(self, minecraft_world_position):
        return tuple(self.botw[i] + (minecraft_world_position[i] - self.mc[i]) * self.scale
                     for i in range(3))


def _ordered_sections(sections, anchor):
    return sorted(sections.values(), key=lambda s: (
        (s[0]*16 - anchor.mc[0])**2 +
        (s[1]*16 - anchor.mc[1])**2 +
        (s[2]*16 - anchor.mc[2])**2,
        s[:3],
    ))


def world_vertices(sections, anchor: WorldAnchor, max_vertices=MAX_VERTICES):
    """Yield triangles in WORLD coordinates; never multiply by a view matrix."""
    if max_vertices < 3 or max_vertices % 3:
        raise ValueError("max_vertices must be positive multiple of 3")
    output = []
    for sx, sy, sz, count, data in _ordered_sections(sections, anchor):
        if count * VERTEX.size != len(data) or count % 3:
            continue
        for base in range(0, count, 3):
            triangle = []
            for j in range(3):
                x, y, z, u, v, color, light, flags = legacy.RENDER_VERTEX.unpack_from(
                    data, (base + j) * legacy.RENDER_VERTEX_BYTES)
                if not all(math.isfinite(f) for f in (x, y, z, u, v)):
                    triangle = []
                    break
                hx, hy, hz = anchor.to_hyrule(
                    (sx*16 + x, sy*16 + y, sz*16 + z))
                if not all(math.isfinite(f) and abs(f) < 100_000 for f in (hx,hy,hz)):
                    triangle = []
                    break
                # Preserve the SkyCraft-provided atlas coordinates, ARGB tint,
                # packed emissive/sky light, alpha and face direction flags.
                triangle.append((hx,hy,hz,u,v,color,light,flags))
            if len(triangle) == 3:
                output.extend(triangle)
                if len(output) >= max_vertices:
                    return output
    return output


def pack(frame: int, anchor: WorldAnchor, vertices):
    if type(frame) is not int or not (0 <= frame <= 0xffffffff):
        raise ValueError("invalid frame sequence")
    if len(vertices) > MAX_VERTICES or len(vertices) % 3:
        raise ValueError("invalid vertex count")
    payload = bytearray()
    for item in vertices:
        if len(item) != 8:
            raise ValueError("bad SkyCraft vertex")
        if not all(math.isfinite(f) for f in item[:5]):
            raise ValueError("non-finite world mesh")
        payload.extend(VERTEX.pack(*item))
    head = HEADER.pack(MAGIC, VERSION, frame, len(vertices), legacy.fnv1a(payload),
                       0,0,0,*anchor.mc,*anchor.botw)
    return head + payload


def validate(packet):
    if len(packet) < HEADER.size or len(packet) > HEADER.size + MAX_VERTICES * VERTEX.size:
        return False
    try:
        vals = HEADER.unpack_from(packet)
    except struct.error:
        return False
    magic, version, frame, count, hash_value = vals[:5]
    if magic != MAGIC or version != VERSION or count > MAX_VERTICES or count % 3:
        return False
    payload = packet[HEADER.size:]
    if len(payload) != count * VERTEX.size or legacy.fnv1a(payload) != hash_value:
        return False
    return all(math.isfinite(n) for n in vals[8:])


def packet_from_sections(sections, mc_origin, link_origin, frame=0):
    anchor = WorldAnchor(mc=tuple(mc_origin), botw=tuple(link_origin))
    verts = world_vertices(sections, anchor)
    return pack(frame, anchor, verts)
