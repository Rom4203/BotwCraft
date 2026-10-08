"""Validate SkyCraft v11 overlay control/header parser without a GPU."""
import struct
import unittest
from botw.hud_overlay import decode_slot_header, OFF_HDR

class OverlayTests(unittest.TestCase):
    def make_read(self, width, height, flags=1, frame=42, slot=1):
        data = bytearray(0x600)
        struct.pack_into("<III", data, OFF_HDR + slot * 64, width, height, flags)
        struct.pack_into("<Q", data, OFF_HDR + slot * 64 + 0x10, frame)
        return lambda offset, size: bytes(data[offset:offset + size])

    def test_reads_actual_skycraft_v11_slot(self):
        reader = self.make_read(1280, 720, flags=1, frame=31)
        self.assertEqual(decode_slot_header(reader, 1), (1, 1280, 720, True, 31))

    def test_requires_real_completed_frame(self):
        for width, height, frame in ((1280, 720, 0), (0, 720, 99),
                                      (4000, 720, 1), (1280, 3000, 1)):
            with self.subTest(width=width, height=height, frame=frame):
                self.assertIsNone(decode_slot_header(
                    self.make_read(width, height, frame=frame), 1))

    def test_invalid_slot_does_not_read_past_mapping(self):
        called = []
        def read(offset, size):
            called.append((offset, size))
            raise AssertionError("should not read")
        self.assertIsNone(decode_slot_header(read, 3))
        self.assertEqual(called, [])

    def test_bottom_up_flag(self):
        read = self.make_read(640, 360, flags=0)
        self.assertEqual(decode_slot_header(read, 1)[3], False)

if __name__ == "__main__":
    unittest.main()
