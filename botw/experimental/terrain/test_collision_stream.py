import tempfile
import unittest
from pathlib import Path
import collision_stream as cs

class CollisionTests(unittest.TestCase):
    def test_parse_and_translate(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'slope.obj'
            path.write_text('v 10 2 20\nv 11 2 20\nv 10 3 21\nf 1/1/1 2/2/2 3/3/3\n')
            tris = cs.parse_obj(path)
            groups = cs.convert_faces(tris, (10, 2, 20), (100, 60, 100))
            self.assertTrue(groups)
            self.assertEqual(sum(map(len, groups.values())), 1)
            a, b, c = next(iter(groups.values()))[0][:3]
            self.assertEqual((a,b,c), (100.,60.,100.))
    def test_packets_are_correct_and_aligned(self):
        groups = {(0,1,-1):[(1.,8.,-8., 2.,8.,-8., 1.,8.,-7.)]}
        packets=list(cs.collision_packets(groups, 123))
        self.assertEqual([int.from_bytes(p[:4],'little') for p in packets],[1,3])
        self.assertTrue(all(len(p)%8==0 for p in packets))
        self.assertEqual(int.from_bytes(packets[1][8+28:8+32],'little'),1)
        self.assertEqual(int.from_bytes(packets[1][8+32+36:8+32+40],'little'),cs.TRI_TERRAIN)
    def test_missing_mesh_and_bad_index(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'bad.obj'
            path.write_text('v 1 2 3\nf 1 2 3\n')
            with self.assertRaises(ValueError):cs.parse_obj(path)
            path.write_text('v 1 2 3\n')
            with self.assertRaises(ValueError):cs.parse_obj(path)
    def test_large_mesh_refusal(self):
        huge=[((0.,0.,0.),(100000.,0.,0.),(0.,0.,1.))]
        with self.assertRaises(ValueError):cs.convert_faces(huge,(0,0,0),(0,0,0))

if __name__=='__main__':unittest.main()