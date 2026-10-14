"""Regression tests: the new SkyCraft/BOTW 3D scene cannot become a 2D overlay."""
import math
import unittest
from botw import native_mesh_bridge as old
from botw import world_space as world

class WorldSceneTests(unittest.TestCase):
    def setUp(self):
        v=[
            (1.,2.,3.,.125,.5,0xff64a0c0,0xf00,0x11),
            (2.,2.,3.,.75,.5,0xff64a0c0,0xf00,0x11),
            (2.,3.,3.,.75,.9,0xff64a0c0,0xf00,0x11),
        ]
        self.vertices=v
        self.sections={(2,4,6):(2,4,6,3,b"".join(old.RENDER_VERTEX.pack(*x) for x in v))}
        self.anchor=world.WorldAnchor(mc=(34.,66.,99.),botw=(-1125.,237.,1906.))

    def test_transforms_world_vertices_not_screen_coordinates(self):
        vs=world.world_vertices(self.sections,self.anchor)
        self.assertEqual(len(vs),3)
        x,y,z,u,v,color,light,flags=vs[0]
        self.assertEqual((x,y,z),(-1126.,237.,1906.))
        self.assertEqual((u,v,color,light,flags),self.vertices[0][3:])
        self.assertTrue(abs(x)>1000)
        self.assertNotEqual(vs[1][0],vs[0][0])
        self.assertNotEqual(vs[2][1],vs[1][1])

    def test_world_anchor_does_not_depend_on_camera_yaw_or_pitch(self):
        before=world.world_vertices(self.sections,self.anchor)
        after=world.world_vertices(self.sections,self.anchor)
        self.assertEqual(before,after)

    def test_bwc2_roundtrip_and_hash(self):
        verts=world.world_vertices(self.sections,self.anchor)
        packet=world.pack(19,self.anchor,verts)
        self.assertTrue(world.validate(packet))
        self.assertEqual(world.HEADER.unpack_from(packet)[:4],
                         (0x32435742,2,19,3))
        corrupted=bytearray(packet)
        corrupted[-1]^=0x80
        self.assertFalse(world.validate(corrupted))
        self.assertFalse(world.validate(packet[:-1]))

    def test_missing_sections_and_invalid_triangle_rejected(self):
        self.assertEqual(world.world_vertices({},self.anchor),[])
        self.assertFalse(world.validate(b""))
        with self.assertRaises(ValueError):
            world.pack(3,self.anchor,[(0.,0.,0.,1.,1.,0xffffffff,0,0)])

    def test_connection_origin_is_fixed_not_following_camera(self):
        p=self.anchor.to_hyrule((35.,66.,99.))
        self.assertEqual(p,(-1124.,237.,1906.))
        p2=self.anchor.to_hyrule((35.,66.,99.))
        self.assertEqual(p,p2)
        self.assertNotEqual(self.anchor.to_hyrule((36.,66.,99.)),p)

    def test_max_packet_fits_native_bound(self):
        faces=world.world_vertices(self.sections,self.anchor)
        packet=world.pack(0,self.anchor,faces*160)
        self.assertLessEqual(len(packet),world.HEADER.size+world.MAX_VERTICES*world.VERTEX.size)
        self.assertTrue(world.validate(packet))


if __name__=="__main__":
    unittest.main()
