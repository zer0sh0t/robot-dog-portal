import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('fire_detector', Path(__file__).parents[1] / 'scripts/fire_detector.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class Tests(unittest.TestCase):
    def setUp(self):
        self.d = module.Detector()

    def feed(self, t, smoke, camera):
        self.d.update('smoke', smoke, t)
        self.d.update('camera', camera, t)
        return self.d.evaluate(t)

    def test_startup_unknown(self):
        self.assertEqual(self.d.evaluate(0), (False, True, 'UNKNOWN; SENSOR_FAULT:smoke,camera'))

    def test_transient_ignored(self):
        self.assertFalse(self.feed(0, True, False)[0])
        self.assertFalse(self.feed(0.2, False, False)[0])
        self.assertFalse(self.feed(1, False, False)[0])

    def test_either_sensor_and_both(self):
        for smoke, camera, expected in [(True, False, 'SMOKE_DETECTED'),
                                      (False, True, 'CAMERA_DETECTED'),
                                      (True, True, 'SMOKE_AND_CAMERA')]:
            self.d = module.Detector()
            self.feed(0, smoke, camera)
            self.assertEqual(self.feed(0.6, smoke, camera), (True, False, expected))

    def test_dropout_holds_alarm(self):
        self.feed(0, True, False)
        self.feed(0.6, True, False)
        alert, fault, _ = self.d.evaluate(3)
        self.assertTrue(alert)
        self.assertTrue(fault)
        self.feed(3.1, False, False)
        self.feed(4.1, False, False)
        self.feed(5.1, False, False)
        self.assertFalse(self.feed(6.2, False, False)[0])

    def test_stale_gap_restarts_confirmation(self):
        self.feed(0, True, False)
        self.d.evaluate(3)
        self.assertFalse(self.feed(3.1, True, False)[0])
        self.assertTrue(self.feed(3.7, True, False)[0])

    def test_invalid_input_is_fault(self):
        alert, fault, _ = self.feed(0, False, None)
        self.assertFalse(alert)
        self.assertTrue(fault)

    def test_fault_breaks_clear_period(self):
        self.feed(0, True, False)
        self.feed(0.6, True, False)
        self.feed(1, False, False)
        self.d.evaluate(3.1)
        self.assertTrue(self.feed(4.1, False, False)[0])


if __name__ == '__main__':
    unittest.main()

