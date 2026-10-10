"""Test real Link control conversion without ViGEm driver or Zelda."""
import math
import struct
import unittest
from botw import steve_controller as sc
from botw import host_bridge as hb

FLAGS = 1 | sc.FPS | sc.INPUTS

def pose(frame,x=10,y=80,z=20,yaw=0,pitch=0,flags=FLAGS):
    return sc.McPose(frame,x,y,z,yaw,pitch,flags)


class ControllerTests(unittest.TestCase):
    def test_steve_forward_drives_link_forward(self):
        a=pose(1)
        b=pose(2,z=20+4.32/20)
        out=sc.convert(a,b,.05)
        self.assertAlmostEqual(out.left_y,1.0,places=4)
        self.assertAlmostEqual(out.left_x,0.0,places=4)

    def test_steve_strafe_relative_to_mc_camera(self):
        a=pose(1,yaw=90)
        b=pose(2,x=10+4.32/20,yaw=90)
        out=sc.convert(a,b,.05)
        self.assertAlmostEqual(out.left_y,-1.0,places=4)
        self.assertAlmostEqual(out.left_x,0.0,places=4)

    def test_mouse_yaw_wrap_and_pitch(self):
        a=pose(1,yaw=179,pitch=5)
        b=pose(2,yaw=-179,pitch=7)
        o=sc.convert(a,b,.05)
        self.assertAlmostEqual(o.right_x,-2/.05/120,places=4)
        self.assertAlmostEqual(o.right_y,-2/.05/120,places=4)

    def test_no_input_on_gui_disconnect_teleport_or_pause(self):
        a=pose(1)
        b=pose(2,z=10000)
        self.assertEqual(sc.convert(a,b,.02),sc.Sticks())
        b=pose(2,z=21,flags=1)
        self.assertEqual(sc.convert(a,b,.02),sc.Sticks())
        processor=sc.Driver()
        self.assertEqual(processor.step(a,False,1),sc.Sticks())
        processor.step(a,True,2)
        processor.step(pose(2,z=20.12),True,2.05)
        self.assertNotEqual(processor.out,sc.Sticks())
        self.assertEqual(processor.step(pose(2,z=20.12),True,2.31),sc.Sticks())
        self.assertEqual(processor.step(pose(3,z=20.3),False,2.33),sc.Sticks())

    def test_mc_state_seqlock(self):
        mem=bytearray(0x1000)
        b=hb.OFF_MC_STATE
        struct.pack_into("<II",mem,b,2,FLAGS)
        struct.pack_into("<ddd",mem,b+8,1,2,3)
        struct.pack_into("<ff",mem,b+0x20,40,-10)
        struct.pack_into("<Q",mem,b+0x38,5)
        self.assertEqual(sc.mc_state(mem),pose(5,1,2,3,40,-10))
        struct.pack_into("<I",mem,b,3)
        self.assertIsNone(sc.mc_state(mem))
        struct.pack_into("<II",mem,b,4,FLAGS)
        struct.pack_into("<ddd",mem,b+8,float("nan"),2,3)
        self.assertIsNone(sc.mc_state(mem))

    def test_zelda_heartbeat_fails_closed(self):
        mem=bytearray(0x1000)
        struct.pack_into("<II",mem,0,hb.MAGIC,hb.VERSION)
        struct.pack_into("<Q",mem,0x10,1100)
        struct.pack_into("<II",mem,hb.OFF_SKY_STATE,2,1)
        struct.pack_into("<ddd",mem,hb.OFF_SKY_STATE+0x10,-1126,237,1910)
        self.assertTrue(sc.real_link_live(mem,1200))
        self.assertFalse(sc.real_link_live(mem,4000))
        struct.pack_into("<I",mem,hb.OFF_SKY_STATE+4,0)
        self.assertFalse(sc.real_link_live(mem,1200))


if __name__=="__main__":
    unittest.main()
