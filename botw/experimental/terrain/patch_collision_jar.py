#!/usr/bin/env python3
"""Patch *only* the SkyClient.linked() call within EntityCollideMixin.

Other code paths (world takeover, teleport, menu, camera, input, renderer,
physics outside local player) remain exactly as in the working test20 jar.
No raw-method rewriting or class-version downgrade occurs.
"""
import hashlib
import io
import struct
import sys
import zipfile
from pathlib import Path

TARGET = 'dev/skycraft/client/mixin/EntityCollideMixin.class'
HELPER = 'dev/skycraft/client/BotwCollisionGate.class'
OLD = b'dev/skycraft/client/SkyClient'
NEW = b'dev/skycraft/client/BotwCollisionGate'

def patch_class(data: bytes) -> bytes:
    if data[:4] != b'\xca\xfe\xba\xbe':
        raise ValueError('Invalid class')
    cp_count = struct.unpack_from('>H', data, 8)[0]
    pos = 10
    out = bytearray(data[:pos])
    replaced = 0
    index = 1
    while index < cp_count:
        tag = data[pos]
        out.append(tag)
        pos += 1
        if tag == 1:
            size = struct.unpack_from('>H', data, pos)[0]
            pos += 2
            value = data[pos:pos + size]
            pos += size
            if value == OLD:
                replaced += 1
                value = NEW
            out.extend(struct.pack('>H', len(value)))
            out.extend(value)
        else:
            size = {3:4,4:4,5:8,6:8,7:2,8:2,9:4,10:4,11:4,
                    12:4,15:3,16:2,17:4,18:4,19:2,20:2}.get(tag)
            if size is None or pos + size > len(data):
                raise ValueError('Invalid constant pool')
            out.extend(data[pos:pos + size])
            pos += size
            if tag in (5, 6):
                index += 1
        index += 1
    if replaced != 1:
        raise ValueError('Unexpected collision mixin layout; refusing patch')
    out.extend(data[pos:])
    return bytes(out)


def patch(jar: Path, helper: Path, out_path: Path):
    original_sha = hashlib.sha256(jar.read_bytes()).hexdigest()
    if helper.read_bytes()[:4] != b'\xca\xfe\xba\xbe':
        raise ValueError('Compile BotwCollisionGate.java first')
    with zipfile.ZipFile(jar) as src:
        names = src.namelist()
        if names.count(TARGET) != 1 or HELPER in names:
            raise ValueError('Unsupported JAR; existing gate or missing mixin')
        old_class = src.read(TARGET)
        if OLD not in old_class or NEW in old_class:
            raise ValueError('Not the original collision class')
        with zipfile.ZipFile(out_path, 'w') as dst:
            for info in src.infolist():
                body = src.read(info)
                if info.filename == TARGET:
                    body = patch_class(body)
                dst.writestr(info, body)
            dst.writestr(HELPER, helper.read_bytes(), compress_type=zipfile.ZIP_DEFLATED)
    with zipfile.ZipFile(jar) as src, zipfile.ZipFile(out_path) as dst:
        changes = [name for name in src.namelist() if src.read(name) != dst.read(name)]
        assert changes == [TARGET], changes
        assert dst.read('dev/skycraft/client/SkyClient.class') == src.read('dev/skycraft/client/SkyClient.class')
        assert dst.read('dev/skycraft/client/BotwCraftSession.class') == src.read('dev/skycraft/client/BotwCraftSession.class')
    print('OK: test20 preserved except collision gate', original_sha)
    print('New experimental jar:', out_path)

if __name__ == '__main__':
    if len(sys.argv) != 4:
        sys.exit('usage: patch_collision_jar.py original.jar BotwCollisionGate.class out.jar')
    patch(*map(Path, sys.argv[1:]))