"""HUD snapshot parsing/PNG tests use a fake view, not Windows or Minecraft."""
import struct
import unittest
import zlib

from botw import hud_snapshot as hud


class FakeMapping:
    def __init__(self,control=0):
        self.small=bytearray(4096)
        struct.pack_into("<I",self.small,hud.OFF_OVERLAY_CTL,control)
        self.pixels=b""

    def __getitem__(self,key):
        if isinstance(key,slice):
            if key.start>=hud.host.OFF_OVERLAY_PIXELS:
                return self.pixels
            return self.small[key]
        return self.small[key]


class HudCaptureTests(unittest.TestCase):
    def test_snapshot_matches_original_triple_buffer_and_frame_id(self):
        fake=FakeMapping(control=1|hud.OVERLAY_DIRTY)
        hdr=hud.OFF_OVERLAY_SLOT_HDR+hud.SLOT_HDR_SIZE
        struct.pack_into("<III",fake.small,hdr,2,1,0)
        struct.pack_into("<Q",fake.small,hdr+hud.SH_FRAME_ID,9)
        fake.pixels=bytes([255,0,0,255, 0,255,0,255])
        result=hud.read_latest(fake)
        self.assertEqual(result,(2,1,False,9,fake.pixels))
        png=hud.make_png(*((result[0],result[1],result[2],result[4])))
        self.assertEqual(png[:8],b"\x89PNG\r\n\x1a\n")

    def test_no_frame_before_enabled_and_invalid_dimension(self):
        fake=FakeMapping()
        self.assertIsNone(hud.read_latest(fake))
        struct.pack_into("<I",fake.small,hud.OFF_OVERLAY_CTL,3|4)
        self.assertIsNone(hud.read_latest(fake))  # invalid slot

    def test_vertical_flip_is_exact(self):
        # Two pixels vertically: red top, blue bottom.
        top=bytes([255,0,0,255])
        bottom=bytes([0,0,255,255])
        image=hud.make_png(1,2,True,bottom+top)
        offset=8
        while offset<len(image):
            size=int.from_bytes(image[offset:offset+4],"big")
            kind=image[offset+4:offset+8]
            if kind==b"IDAT":
                payload=image[offset+8:offset+8+size]
                decoded=zlib.decompress(payload)
                self.assertEqual(decoded,b"\x00"+top+b"\x00"+bottom)
                return
            offset+=12+size
        self.fail("missing PNG IDAT")


if __name__=="__main__":
    unittest.main()
