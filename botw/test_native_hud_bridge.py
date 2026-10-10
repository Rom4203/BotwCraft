"""BWH1 native HUD pixel integrity and viewport-scale tests."""
from pathlib import Path
from tempfile import TemporaryDirectory
import struct
import time
import unittest

from botw import native_hud_bridge as hud
from botw import gdb_mesh_bridge as gdb


class NativeHudTests(unittest.TestCase):
    def test_real_rgba_gpu_frame_downsample_and_flip(self):
        # Top row red, bottom blue in a 2x2 bottom-up capture.
        blue=bytes((0,0,255,255))
        red=bytes((255,0,0,255))
        frame=(2,2,True,7,blue*2+red*2)
        packet=hud.make_packet(frame)
        self.assertEqual(len(packet),hud.CAPACITY)
        head=hud.HEADER.unpack_from(packet)
        self.assertEqual(head[:6], (hud.MAGIC,1,7,128,72,36864))
        self.assertEqual(head[6],hud.hash_pixels(packet[hud.HEADER.size:]))
        self.assertEqual(packet[hud.HEADER.size:hud.HEADER.size+4],red)
        self.assertEqual(packet[-4:],blue)

    def test_no_fake_or_stale_guest_address(self):
        with TemporaryDirectory() as folder:
            file=Path(folder)/"live.log"
            file.write_text(gdb.VERSION+"\n"
                            "BotwCraft:NATIVE_HUD_BUFFER_ADDR=0x0000000012345000\n"
                            "BotwCraft:NATIVE_HUD_CAPACITY=36896\n")
            self.assertEqual(hud.current_native_hud_mailbox(file),0x12345000)
            file.write_text("Game: build 0x6811B941\n"
                            "BotwCraft:NATIVE_HUD_BUFFER_ADDR=0x0000000012345000\n"
                            "BotwCraft:NATIVE_HUD_CAPACITY=36896\n")
            self.assertIsNone(hud.current_native_hud_mailbox(file))
            file.write_text(gdb.VERSION+"\n"
                            "BotwCraft:NATIVE_HUD_CAPACITY=36896\n")
            self.assertIsNone(hud.current_native_hud_mailbox(file))

    def test_invalid_rgba_rejected(self):
        with self.assertRaises(ValueError):
            hud.downsample_rgba(128,72,False,b"not RGBA")


if __name__=="__main__":
    unittest.main()
