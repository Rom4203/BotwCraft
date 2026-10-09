"""Test actual SkyCraft render-ring messages -> native WiiXLaunch mesh packets."""
import mmap
from pathlib import Path
import struct
from tempfile import TemporaryDirectory
import unittest

from botw import native_mesh_bridge as native

class NativeMeshTests(unittest.TestCase):
    def test_native_header_and_64bit_coordinates(self):
        packet = native.encode_mesh(27, [
            (-.5, -.5, .5, 1., 1., 0., 0., 1.),
            ( .5, -.5, .5, 1., 1., 0., 0., 1.),
            ( .0,  .5, .5, 1., 1., 0., 0., 1.),
        ])
        header = native.HEADER.unpack_from(packet)
        self.assertEqual(header[:4], (0x31435742, 1, 27, 3))
        self.assertEqual(header[4], native.fnv1a(packet[32:]))
        self.assertEqual(len(packet), 32 + 3*32)
        self.assertEqual(native.encode_mesh(7, [])[:20],
                         native.HEADER.pack(0x31435742, 1, 7, 0,
                                            native.fnv1a(b""), 0, 0, 0)[:20])

    def test_bad_triangles_cannot_reach_native_code(self):
        with self.assertRaises(ValueError):
            native.encode_mesh(1, [(0., 0., 0., 1., 1., 0., 0., 1.)])
        with self.assertRaises(ValueError):
            native.encode_mesh(1, [(float("nan"), 0, 0, 1, 0, 0, 0, 1)]*3)

    def test_real_skyscript_section_tris_are_projected(self):
        camera = (0., 80., 0., 0., 0.)
        vertex = native.RENDER_VERTEX.pack(0., 2., 6., 0., 0., 0xffffffff, 0, 0)
        sections = {(0, 5, 0): (0, 5, 0, 3, vertex*3)}
        verts = native.sections_to_mesh(sections, camera)
        self.assertEqual(len(verts), 3)
        self.assertTrue(all(v[3] == 1 for v in verts))

    def test_mc_projection_rejects_behind_camera(self):
        camera = (0., 80., 0., 0., 0.)
        self.assertIsNone(native.project((0., 80., -9.), camera))
        self.assertIsNotNone(native.project((0., 82., 9.), camera))

    def test_render_ring_consumes_real_section_payload_and_clear(self):
        size = native.OFF_RENDER_RING + 1024
        with mmap.mmap(-1, size) as memory:
            ring = native.OFF_RENDER_RING
            verts = native.RENDER_VERTEX.pack(0., 2., 6., 0., 0., 0xffffffff, 0, 0)*3
            body = native.SECTION.pack(0, 5, 0, 3) + verts
            event = struct.pack("<II", native.RENDER_SECTION, len(body)) + body
            event += bytes((-len(event)) % 8)
            struct.pack_into("<Q", memory, ring, len(event))
            memory[ring+native.RENDER_RING_DATA:ring+native.RENDER_RING_DATA+len(event)] = event
            messages, count = native.decode_render_ring(memory)
            self.assertEqual(count, 1)
            self.assertEqual(len(messages), 1)
            self.assertEqual(messages[0][0], "section")
            self.assertEqual(messages[0][1][3], 3)
            self.assertEqual(struct.unpack_from("<Q", memory, ring+0x40)[0],
                             len(event))

    def test_atomic_writes_do_not_leave_partial_filenames(self):
        with TemporaryDirectory() as directory:
            destination = Path(directory) / native.DEFAULT_RELATIVE_PATH
            packet = native.encode_mesh(1, [])
            native.write_atomic(destination, packet)
            self.assertEqual(destination.read_bytes(), packet)
            self.assertFalse(destination.with_name("frame.bin.part").exists())

if __name__ == "__main__":
    unittest.main()
