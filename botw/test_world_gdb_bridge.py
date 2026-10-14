"""BWC2 GDB world source tests (no game, no 2D screen projection)."""
from pathlib import Path
from tempfile import TemporaryDirectory
import struct
import time
import unittest

from botw import world_gdb_bridge as bridge
from botw import gdb_mesh_bridge as gdb

class WorldSourceTests(unittest.TestCase):
    def test_world_buffer_is_reported_only_by_correct_current_native_module(self):
        with TemporaryDirectory() as folder:
            p=Path(folder)/"live.log"
            p.write_text(gdb.VERSION+"\n"
                         "BotwCraft:BWC2_WORLD_BUFFER_ADDR=0x0000000012345000\n"
                         "BotwCraft:BWC2_WORLD_BUFFER_CAPACITY=15416\n")
            self.assertEqual(bridge.latest_world_mailbox(p),0x12345000)
            p.write_text("Game: build 0x6811B941\n"
                         "BotwCraft:BWC2_WORLD_BUFFER_ADDR=0x0000000012345000\n"
                         "BotwCraft:BWC2_WORLD_BUFFER_CAPACITY=15416\n")
            self.assertIsNone(bridge.latest_world_mailbox(p))

    def test_link_pose_reads_v11_seqlock(self):
        block=bytearray(0x200)
        off=bridge.OFF_SKY_STATE
        struct.pack_into("<II",block,off,2,1)
        struct.pack_into("<3d",block,off+0x10,-1125.0,237.0,1906.0)
        self.assertEqual(bridge.link_world_position(block),(-1125.,237.,1906.))
        struct.pack_into("<I",block,off,3)
        self.assertIsNone(bridge.link_world_position(block))
        struct.pack_into("<II",block,off,4,0)
        self.assertIsNone(bridge.link_world_position(block))

if __name__=="__main__":
    unittest.main()
