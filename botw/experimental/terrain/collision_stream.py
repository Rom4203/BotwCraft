#!/usr/bin/env python3
"""Experimental BOTW OBJ -> existing SkyCraft v11 triangle collision ring.

DOES NOT extract Zelda collisions, move Link, touch Ryujinx, or teleport Minecraft.
Requires an actual world-aligned Hyrule collision OBJ to be supplied separately.
Windows: opens a PRE-EXISTING bridge mapping (does not create or own it).
"""
from __future__ import annotations

import argparse
import ctypes
import math
import os
from pathlib import Path
import struct
import sys
import time
from collections import defaultdict

MAP_NAME = 'Local\\SkyCraft_v1'
MAGIC, VERSION = 0x43594B53, 11
OFF_MC, OFF_SKY = 0x200, 0x100
OFF_RING, RING_SIZE = 0x20000, 32 << 20
CR_HEAD, CR_TAIL, CR_DATA = OFF_RING, OFF_RING + 0x40, OFF_RING + 0x80
CR_DATA_BYTES = RING_SIZE - 0x80
COL_PAD, COL_CLEAR, COL_REGION, COL_TRIS = 0, 1, 2, 3
REGION_SIZE = 8
TRI_TERRAIN = 8
MAX_FACES = 250_000
MAX_REGIONS = 16_000
MAX_TRIS_PER_REGION = 4096


def coords(v):
    return all(math.isfinite(x) and abs(x) < 100_000 for x in v)


def parse_obj(path: Path, max_faces=MAX_FACES):
    """Read small collision OBJ with triangular / polygonal faces. No materials."""
    vertices = []
    faces = []
    with path.open('r', encoding='utf-8-sig', errors='replace') as fh:
        for line in fh:
            line = line.strip()
            if line.startswith('v '):
                values = line.split()
                if len(values) < 4:
                    raise ValueError('Invalid OBJ vertex')
                xyz = tuple(map(float, values[1:4]))
                if not coords(xyz):
                    raise ValueError('Non-finite OBJ vertex')
                vertices.append(xyz)
                if len(vertices) > max_faces * 3:
                    raise ValueError('Too many vertices; divide the OBJ')
            elif line.startswith('f '):
                indices = []
                for name in line.split()[1:]:
                    i = int(name.split('/')[0])
                    idx = i - 1 if i > 0 else len(vertices) + i
                    if idx < 0 or idx >= len(vertices):
                        raise ValueError('OBJ face vertex index out of range')
                    indices.append(idx)
                if len(indices) < 3 or len(indices) > 256:
                    raise ValueError('Unsupported OBJ face vertex count')
                for j in range(1, len(indices) - 1):
                    faces.append((vertices[indices[0]], vertices[indices[j]], vertices[indices[j + 1]]))
                    if len(faces) > max_faces:
                        raise ValueError('OBJ too large; export a smaller area')
    if not faces:
        raise ValueError('No mesh faces found in OBJ')
    return faces


def convert_faces(faces, botw_origin, mc_origin, radius=48):
    """Translate world coordinates into the bridge's 1 BOTW unit = 1 MC block frame."""
    groups = defaultdict(list)
    for triangle in faces:
        shifted = [tuple(v[i] - botw_origin[i] + mc_origin[i] for i in range(3)) for v in triangle]
        xmin, xmax = min(v[0] for v in shifted), max(v[0] for v in shifted)
        ymin, ymax = min(v[1] for v in shifted), max(v[1] for v in shifted)
        zmin, zmax = min(v[2] for v in shifted), max(v[2] for v in shifted)
        if xmax < mc_origin[0] - radius or xmin > mc_origin[0] + radius or \
           ymax < mc_origin[1] - radius or ymin > mc_origin[1] + radius or \
           zmax < mc_origin[2] - radius or zmin > mc_origin[2] + radius:
            continue
        ranges = [range(math.floor(vmin / REGION_SIZE), math.floor(vmax / REGION_SIZE) + 1)
                  for vmin, vmax in ((xmin, xmax), (ymin, ymax), (zmin, zmax))]
        cells = math.prod(len(r) for r in ranges)
        if cells > 4096:
            raise ValueError('A triangle spans too many collision regions')
        flat = (*shifted[0], *shifted[1], *shifted[2])
        if not coords(flat):
            raise ValueError('Coordinate overflow')
        for x in ranges[0]:
            for y in ranges[1]:
                for z in ranges[2]:
                    region = (x, y, z)
                    groups[region].append(flat)
                    if len(groups[region]) > MAX_TRIS_PER_REGION:
                        raise ValueError('Too many triangles in 8x8x8 region')
                    if len(groups) > MAX_REGIONS:
                        raise ValueError('Too many regions')
    if not groups:
        raise ValueError('No triangles near the player (check BOTW origin / scale)')
    return groups


def pack_packet(kind, payload):
    return struct.pack('<II', kind, len(payload)) + payload + b'\0' * (-(len(payload) + 8) % 8)


def collision_packets(groups, epoch):
    yield pack_packet(COL_CLEAR, struct.pack('<I', epoch))
    for (rx, ry, rz), faces in sorted(groups.items()):
        lo = (rx * REGION_SIZE, ry * REGION_SIZE, rz * REGION_SIZE)
        hi = tuple(v + REGION_SIZE - 1 for v in lo)
        # Avoid COL_REGION: 8x8x8 voxel rebuilds per cell can stall Minecraft.
        # The smooth triangle collider only needs COL_TRIS.
        header = struct.pack('<8i', *lo, *hi, epoch, len(faces))
        tris = b''.join(struct.pack('<9fi', *face, TRI_TERRAIN) for face in faces)
        yield pack_packet(COL_TRIS, header + tris)


class SharedMemory:
    """Read/write only a pre-existing named mapping; NEVER create a new one."""
    def __init__(self):
        if os.name != 'nt':
            raise OSError('Windows / pre-existing Rust bridge required')
        k32 = ctypes.WinDLL('kernel32', use_last_error=True)
        k32.OpenFileMappingW.argtypes = (ctypes.c_uint32, ctypes.c_int, ctypes.c_wchar_p)
        k32.OpenFileMappingW.restype = ctypes.c_void_p
        k32.MapViewOfFile.argtypes = (ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_size_t)
        k32.MapViewOfFile.restype = ctypes.c_void_p
        k32.UnmapViewOfFile.argtypes = (ctypes.c_void_p,)
        k32.UnmapViewOfFile.restype = ctypes.c_int
        k32.CloseHandle.argtypes = (ctypes.c_void_p,)
        k32.CloseHandle.restype = ctypes.c_int
        self.k32 = k32
        self.handle = k32.OpenFileMappingW(0x0002 | 0x0004, 0, MAP_NAME)
        if not self.handle:
            raise OSError('Bridge absent : START_BOTWCRAFT.bat avant le streamer')
        self.base = k32.MapViewOfFile(self.handle, 0x0002 | 0x0004, 0, 0, 0)
        if not self.base:
            k32.CloseHandle(self.handle)
            raise OSError('MapViewOfFile failed')
        if self.u32(0) != MAGIC or self.u32(4) != VERSION:
            self.close()
            raise OSError('SkyCraft v11 header mismatch')

    def close(self):
        if getattr(self, 'base', None):
            self.k32.UnmapViewOfFile(self.base)
            self.base = None
        if getattr(self, 'handle', None):
            self.k32.CloseHandle(self.handle)
            self.handle = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def u64(self, offset):
        return struct.unpack('<Q', ctypes.string_at(self.base + offset, 8))[0]

    def u32(self, offset):
        return struct.unpack('<I', ctypes.string_at(self.base + offset, 4))[0]

    def f64(self, offset):
        return struct.unpack('<d', ctypes.string_at(self.base + offset, 8))[0]

    def write(self, offset, buf):
        ctypes.memmove(self.base + offset, buf, len(buf))

    def snapshot(self):
        for _ in range(25):
            sky_seq, mc_seq = self.u32(OFF_SKY), self.u32(OFF_MC)
            if sky_seq & 1 or mc_seq & 1:
                time.sleep(.002)
                continue
            sky_flags, mc_flags = self.u32(OFF_SKY + 4), self.u32(OFF_MC + 4)
            botw = tuple(self.f64(OFF_SKY + 16 + i * 8) for i in range(3))
            mc = tuple(self.f64(OFF_MC + 8 + i * 8) for i in range(3))
            if self.u32(OFF_SKY) == sky_seq and self.u32(OFF_MC) == mc_seq:
                if (sky_flags & 1) == 0 or (mc_flags & (1 | 0x20000)) != (1 | 0x20000):
                    raise ValueError('Zelda + Minecraft game + /botwcraft inputs on required')
                if not coords(botw) or not coords(mc):
                    raise ValueError('Invalid MC or BOTW coordinates')
                return botw, mc
        raise TimeoutError('Cannot read a stable game state')

    def push(self, packet, timeout=4.):
        if len(packet) > CR_DATA_BYTES // 4:
            raise ValueError('Oversized collision packet')
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            head, tail = self.u64(CR_HEAD), self.u64(CR_TAIL)
            if tail > head or head - tail > CR_DATA_BYTES:
                raise RuntimeError('Invalid collision ring cursor')
            pos = head % CR_DATA_BYTES
            remaining = CR_DATA_BYTES - pos
            pad = remaining if remaining < len(packet) else 0
            required = len(packet) + pad
            if head - tail + required <= CR_DATA_BYTES:
                if pad:
                    # The consumer interprets PAD as skip-to-end-of-ring.
                    # A short (<8 B) remainder never occurs: ring length and
                    # packets are multiples of eight.
                    self.write(CR_DATA + pos, struct.pack('<II', COL_PAD, 0))
                    head += remaining
                    pos = 0
                self.write(CR_DATA + pos, packet)
                # Release/publish last. Single producer, consumed by Fabric.
                self.write(CR_HEAD, struct.pack('<Q', head + len(packet)))
                return
            time.sleep(.01)
        raise TimeoutError('Minecraft is not consuming collision packets')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('obj', type=Path, help='A real BOTW terrain/collision OBJ in BOTW world coordinates')
    parser.add_argument('--radius', type=int, default=48, help='Area near player in game units (default 48)')
    parser.add_argument('--dry-run', action='store_true', help='Parse/test geometry without connecting to Windows')
    parser.add_argument('--botw-origin', type=float, nargs=3, metavar=('X','Y','Z'))
    parser.add_argument('--mc-origin', type=float, nargs=3, metavar=('X','Y','Z'))
    args = parser.parse_args(argv)
    if args.radius < 8 or args.radius > 256:
        parser.error('Radius must be between 8 and 256')
    faces = parse_obj(args.obj)
    if args.dry_run:
        if not (args.botw_origin and args.mc_origin):
            parser.error('--dry-run requires --botw-origin and --mc-origin')
        groups = convert_faces(faces, args.botw_origin, args.mc_origin, args.radius)
        packets = list(collision_packets(groups, 1))
        print('VALID', len(faces), 'triangles', len(groups), 'regions', sum(map(len, packets)), 'bytes')
        return
    with SharedMemory() as mem:
        botw, mc = mem.snapshot()
        time.sleep(.2)
        botw2, mc2 = mem.snapshot()
        if math.dist(mc, mc2) > 0.06:
            raise ValueError('Stop moving Minecraft before sampling the origin')
        groups = convert_faces(faces, botw2, mc2, args.radius)
        # Fresh epoch ensures all old cells are removed. Every producer is
        # single-use; do not run two simultaneous copies of this script.
        epoch = (int(time.time()) & 0x7FFFFFFF) or 1
        count = 0
        for packet in collision_packets(groups, epoch):
            mem.push(packet)
            count += 1
        print(f'OK: {sum(map(len, groups.values()))} mesh triangles copied into '
              f'{len(groups)} regions ({count} messages)')
        print('Experimental collisions: only local Minecraft player, press /botwcraft disconnect to disable')

if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, TimeoutError, RuntimeError) as exc:
        sys.exit(f'[BotwCraft terrain] {exc}')