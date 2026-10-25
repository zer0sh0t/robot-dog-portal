"""Synthetic color-mask checks, not an accuracy test on real fires."""
import importlib.util
from pathlib import Path
import unittest

try:
    import cv2
    import numpy as np
except ImportError:
    cv2 = None


@unittest.skipIf(cv2 is None, 'OpenCV/numpy not installed')
class CameraTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location('camera_fire_detector',
            Path(__file__).parents[1] / 'scripts/camera_fire_detector.py')
        cls.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.module)

    def test_black_frame(self):
        frame = np.zeros((240, 320, 3), dtype=np.uint8)
        self.assertEqual(self.module.find_candidates(frame), [])

    def test_orange_region(self):
        frame = np.zeros((240, 320, 3), dtype=np.uint8)
        frame[50:150, 50:150] = (0, 140, 255)
        self.assertTrue(self.module.find_candidates(frame))

    def test_small_orange_region_filtered(self):
        frame = np.zeros((240, 320, 3), dtype=np.uint8)
        frame[50:55, 50:55] = (0, 140, 255)
        self.assertEqual(self.module.find_candidates(frame), [])


if __name__ == '__main__':
    unittest.main()

