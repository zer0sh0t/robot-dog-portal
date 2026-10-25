import unittest
from reasoning import from_sensors
from sensor_state import SensorState


class ReasoningTest(unittest.TestCase):
    def setUp(self):
        self.now = 10
        self.sensors = SensorState(clock=lambda: self.now)

    def feed(self, camera=False, smoke=False, fault=False):
        for key, value in [('camera', camera), ('smoke_detected', smoke),
                           ('fire_sensor_fault', fault), ('fire_alert', camera or smoke)]:
            self.sensors.update(key, value)
        return from_sensors(self.sensors.snapshot())

    def test_offline_at_startup(self):
        self.assertEqual(from_sensors(self.sensors.snapshot())['status'], 'FAULT')

    def test_normal_without_temperature(self):
        result = self.feed()
        self.assertEqual(result['status'], 'OK')
        self.assertIsNone(result['baseline_v'])
        self.assertIsNone(result['reading_v'])

    def test_camera_or_smoke_recommends_stop(self):
        for kwargs in ({'camera': True}, {'smoke': True}):
            result = self.feed(**kwargs)
            self.assertEqual(result['status'], 'ALARM')
            self.assertEqual(result['proposed_action'], 'STOP_AND_REPORT')
            self.assertFalse(result['action_executed'])

    def test_fault_and_dropout_never_clear(self):
        self.assertEqual(self.feed(fault=True)['status'], 'FAULT')
        self.feed(camera=True)
        self.now += 11
        result = from_sensors(self.sensors.snapshot())
        self.assertEqual(result['status'], 'FAULT')
        self.assertIn('possible hazard', result['explanation'])
        self.assertEqual(result['proposed_action'], 'STOP_AND_REPORT')
