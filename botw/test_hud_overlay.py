"""Validate SkyCraft v11 overlay control/header parser without a GPU."""
import struct
import unittest
from botw.hud_overlay import (decode_slot_header, remove_void_background,
                              is_ryujinx_executable, OFF_HDR)

class OverlayTests(unittest.TestCase):
    def test_exact_ryujinx_executable_not_browser_title(self):
        self.assertTrue(is_ryujinx_executable(
            r"D:\\Jeux\\Ryujinx\\Ryujinx.exe"))
        self.assertTrue(is_ryujinx_executable(
            "C:/Emu/Ryujinx.Ava.exe"))
        for false_app in (
            r"C:\\Program Files\\Opera\\opera.exe",
            r"C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
            r"D:\\games\\not-ryujinx.exe",
            "", None, "ChatGPT - Ryujinx - Opera",
        ):
            self.assertFalse(is_ryujinx_executable(false_app))


    def make_read(self, width, height, flags=1, frame=42, slot=1):
        data = bytearray(0x600)
        struct.pack_into("<III", data, OFF_HDR + slot * 64, width, height, flags)
        struct.pack_into("<Q", data, OFF_HDR + slot * 64 + 0x10, frame)
        return lambda offset, size: bytes(data[offset:offset + size])

    def test_background_key_preserves_blocks_and_frame_size(self):
        sky = bytes((100, 170, 240, 255))
        stone = bytes((90, 65, 35, 255))
        frame = sky + sky + sky + stone
        result = remove_void_background(frame, 2, 2, tolerance=20)
        self.assertEqual(len(result), len(frame))
        self.assertEqual(result[:12], bytes(12))
        self.assertEqual(result[12:], stone)

    def test_keyer_rejects_bad_length(self):
        with self.assertRaises(ValueError):
            remove_void_background(b"wrong", 10, 10)

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
