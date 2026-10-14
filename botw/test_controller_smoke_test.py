import unittest
from controller_smoke_test import mapped_state

class ControllerInputTests(unittest.TestCase):
    def test_idle(self):
        self.assertEqual(mapped_state(set()).x, 0)
        self.assertEqual(mapped_state(set()).y, 0)
    def test_forward(self):
        self.assertEqual(mapped_state({"W"}).y, 1)
    def test_opposing_keys_cancel(self):
        self.assertEqual(mapped_state({"W", "S", "A", "D"}).x, 0)
        self.assertEqual(mapped_state({"W", "S", "A", "D"}).y, 0)
    def test_diagonal_normalized(self):
        p = mapped_state({"W", "D"})
        self.assertAlmostEqual(p.x ** 2 + p.y ** 2, 1.0)
    def test_actions(self):
        p = mapped_state({"SPACE", "SHIFT", "CTRL"})
        self.assertTrue(p.jump and p.sprint and p.crouch)
