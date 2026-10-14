"""Run: python -m unittest discover -s botw -p 'test_*.py'"""
import unittest
from bridge_math import CoordinateMap, Vector3, IDENTITY_TEST_MAP


class CoordinateMapTests(unittest.TestCase):
    def test_identity(self):
        point = Vector3(13, -5, 42)
        self.assertEqual(IDENTITY_TEST_MAP.to_botw(
            IDENTITY_TEST_MAP.to_minecraft(point)), point)

    def test_swapped_axes_and_scale(self):
        transform = CoordinateMap(
            Vector3(100, 200, 300), Vector3(-50, 8, 17), 2.0,
            Vector3(0, 0, 1), Vector3(0, 1, 0), Vector3(-1, 0, 0))
        sample = Vector3(114, 208, 304)
        mc = transform.to_minecraft(sample)
        self.assertEqual(mc, Vector3(-48, 12, 10))
        for a, b in zip(sample.__dict__.values(),
                        transform.to_botw(mc).__dict__.values()):
            self.assertAlmostEqual(a, b)

    def test_invalid_scale(self):
        with self.assertRaises(ValueError):
            CoordinateMap(Vector3(0,0,0), Vector3(0,0,0), 0,
                          Vector3(1,0,0), Vector3(0,1,0), Vector3(0,0,1))

    def test_invalid_basis(self):
        with self.assertRaises(ValueError):
            CoordinateMap(Vector3(0,0,0), Vector3(0,0,0), 1,
                          Vector3(1,0,0), Vector3(1,0,0), Vector3(0,0,1))


if __name__ == "__main__":
    unittest.main()
