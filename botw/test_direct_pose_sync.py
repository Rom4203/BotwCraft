"""Direct BotwCraft targets are measured world positions, NOT virtual sticks."""
import math
import struct
import unittest
from botw import host_bridge as host
from botw import direct_pose_sync as bdp

FLAGS=1|bdp.INPUTS|bdp.FPS_GUI

def mc(frame=1,xyz=(10.,80.,20.),yaw=0.,pitch=0.,flags=FLAGS,eye=1.62):
    return bdp.Pose(frame,xyz,yaw,pitch,flags,eye)


class DirectPoseTests(unittest.TestCase):
    def test_fixed_zelda_origin_minecraft_delta_and_camera(self):
        a=bdp.Align()
        link=(-1126.,237.,1910.)
        first=a.target(mc(),link)
        self.assertEqual(first.position,link)
        self.assertEqual(first.forward,(0.,-0.,1.))
        self.assertAlmostEqual(first.eye[1],238.62)
        # Exact Minecraft movement, no speed/joystick approximation
        moved=a.target(mc(2,(12.,85.,14.),90.,-30.),link)
        self.assertEqual(moved.position,(-1124.,242.,1904.))
        self.assertAlmostEqual(moved.forward[0],-math.cos(math.radians(30)),places=6)
        self.assertAlmostEqual(moved.forward[1],0.5,places=6)
        self.assertAlmostEqual(moved.forward[2],0.,places=6)

    def test_camera_does_not_shift_game_world_anchor(self):
        a=bdp.Align()
        a.target(mc(),(-1126,237,1910))
        b=a.target(mc(2,yaw=120,pitch=55),(-1000,100,1000))
        self.assertEqual(b.position,(-1126.,237.,1910.))
        self.assertAlmostEqual(math.sqrt(sum(x*x for x in b.forward)),1.)

    def test_menu_disconnect_and_teleport_disarm(self):
        a=bdp.Align()
        self.assertIsNotNone(a.target(mc(),(-1000,200,500)))
        self.assertIsNone(a.target(mc(2,flags=1|bdp.INPUTS),(-1000,200,500)))
        self.assertEqual(a.mc_origin,(10.,80.,20.))
        # The actor may have drifted while a menu was open; same MC origin
        # must still map to the same Hyrule origin.
        self.assertEqual(a.target(mc(3),(-1001,199,498)).position,(-1000.,200.,500.))
        self.assertIsNone(a.target(mc(4,(1000,80,20)),(-1000,200,500)))
        self.assertIsNone(a.mc_origin)
        a.target(mc(5),(-1000,200,500))
        self.assertIsNone(a.target(mc(6,flags=1),(-1000,200,500)))
        self.assertIsNone(a.mc_origin)

    def test_minecraft_and_link_seqlock_and_real_heartbeat(self):
        memory=bytearray(bdp.ADDRESS+bdp.HEADER.size)
        struct.pack_into("<II",memory,0,host.MAGIC,host.VERSION)
        struct.pack_into("<Q",memory,16,1200)
        struct.pack_into("<II",memory,host.OFF_SKY_STATE,2,1)
        struct.pack_into("<ddd",memory,host.OFF_SKY_STATE+0x10,-1126,237,1910)
        self.assertEqual(bdp.get_botw(memory,1300),(-1126.,237.,1910.))
        self.assertIsNone(bdp.get_botw(memory,2301))
        struct.pack_into("<Q",memory,0x18,1200)
        struct.pack_into("<II",memory,host.OFF_MC_STATE,2,FLAGS)
        struct.pack_into("<ddd",memory,host.OFF_MC_STATE+8,10,80,20)
        struct.pack_into("<ff",memory,host.OFF_MC_STATE+0x20,90,-20)
        struct.pack_into("<f",memory,host.OFF_MC_STATE+0x28,1.62)
        struct.pack_into("<Q",memory,host.OFF_MC_STATE+0x38,9)
        self.assertTrue(bdp.ready(bdp.get_minecraft(memory,1300)))
        self.assertIsNone(bdp.get_minecraft(memory,2400))
        struct.pack_into("<I",memory,host.OFF_MC_STATE,3)
        self.assertIsNone(bdp.get_minecraft(memory))

    def test_packet_round_trip_and_safe_disarm(self):
        mem=bytearray(bdp.ADDRESS+bdp.HEADER.size)
        a=bdp.Align()
        target=a.target(mc(),(-1126,237,1910))
        seq=bdp.publish(mem,target,0,1300)
        self.assertEqual(seq,2)
        record=bdp.inspect(mem,1400)
        self.assertEqual(record[:4],(2,bdp.MAGIC,bdp.VERSION,bdp.ACTIVE|bdp.FPS))
        self.assertEqual(tuple(record[6:9]),(-1126.,237.,1910.))
        self.assertIsNone(bdp.inspect(mem,2301))
        seq=bdp.publish(mem,None,seq,2000)
        self.assertEqual(seq,4)
        self.assertIsNone(bdp.inspect(mem,2001))
        struct.pack_into("<I",mem,bdp.ADDRESS,5)
        self.assertIsNone(bdp.inspect(mem,2001))

    def test_no_gamepad_emulation_source(self):
        # Preserve user's strict requirement: directly synchronize transforms.
        from pathlib import Path
        s=(Path(__file__).parent/"direct_pose_sync.py").read_text()
        for forbidden in ("vgamepad","VX360Gamepad","left_joystick_float","right_joystick_float"):
            self.assertNotIn(forbidden,s)


if __name__=="__main__":
    unittest.main()
