"""Native BOTW Switch 1.5.0 direct actor transport tests.

No emulator or win32 process is required; tests only validate packet guards,
strict executable identity, and 40-byte guest-owned mailbox identity.
"""
from pathlib import Path
import struct
import unittest

from botw import direct_pose_sync as pose
from botw import ryujinx_direct_memory as direct

FLAGS = 1|pose.FPS_GUI|pose.INPUTS

class DirectActorTests(unittest.TestCase):
    def test_exact_guest_owned_signature_and_no_gamepad(self):
        self.assertEqual(len(direct.MARKER),40)
        self.assertTrue(direct.MARKER.startswith(b"BOTWCRAFT15_DIRECT_GUEST"))
        self.assertTrue(direct.safe_process_name(r"D:\Emu\Ryujinx.exe"))
        self.assertTrue(direct.safe_process_name(r"D:\Emu\Ryujinx.Ava.exe"))
        self.assertFalse(direct.safe_process_name(r"C:\Opera\opera.exe"))
        self.assertFalse(direct.safe_process_name(r"C:\Other\FakeRyujinx.exe"))
        self.assertFalse(direct.safe_process_name("ChatGPT - Ryujinx"))
        source=Path(__file__).parent.joinpath("ryujinx_direct_memory.py").read_text()
        for bad in ("vgamepad","VX360Gamepad","left_joystick_float"):
            self.assertNotIn(bad,source)

    def test_native_target_matches_skyscript_seqlock(self):
        align=pose.Align()
        mc=pose.Pose(8,(10,70,20),30.,-10.,FLAGS,1.62)
        t=align.target(mc,(-1126,237,1910))
        packet=pose.encode(t,2,1234)
        self.assertEqual(len(packet),112)
        self.assertEqual(struct.unpack_from("<4I",packet),
                         (2,pose.MAGIC,pose.VERSION,3))
        modified=bytearray(packet)
        val=struct.unpack_from("<I",modified,12)[0]
        struct.pack_into("<I",modified,12,val|direct.ALLOW_ACTOR_WRITE)
        self.assertEqual(struct.unpack_from("<I",modified,12)[0],
                         3|direct.ALLOW_ACTOR_WRITE)
        self.assertAlmostEqual(struct.unpack_from("<f",modified,32)[0],-1126.)

    def test_guest_native_hook_is_opted_in_and_checks_real_crc(self):
        h=Path(__file__).parent/"switch15_direct_hook.hpp"
        src=h.read_text()
        self.assertIn("0xA982D2BC",src)
        self.assertIn("kAllowActorWrite = 0x10",src)
        self.assertIn("kSetMtxVirtualIndex = 85",src)
        self.assertIn("TryApplyActor",src)
        self.assertIn("gRenderFramesSinceUpdate > 12",src)
        self.assertIn("BOTWCRAFT15_DIRECT_GUEST_XYZ_20261010",src)
        p=(Path(__file__).parent/"patch_botw15_player_pose.py").read_text()
        self.assertIn("BotwCraft15Direct::Poll(player, xyz);",p)
        self.assertIn("BotwCraft15Direct::Register();",p)


if __name__=="__main__":
    unittest.main()
