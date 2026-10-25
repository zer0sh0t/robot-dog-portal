import json
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from unittest.mock import patch

from sensor_state import SensorState
import server


class SensorsTest(unittest.TestCase):
    def setUp(self):
        self.now = 100
        self.state = SensorState(clock=lambda: self.now)

    def test_independent_updates_and_timeout(self):
        self.assertEqual(self.state.snapshot()['alarm'], 'unknown')
        self.state.update('fire_alert', False)
        self.state.update('smoke', 0)
        self.assertEqual(self.state.snapshot()['alarm'], 'unknown')
        self.state.update('temperature', 25.5)
        self.assertEqual(self.state.snapshot()['alarm'], 'clear')
        self.now += 11
        self.state.update('smoke', 1)
        snapshot = self.state.snapshot()
        self.assertEqual(snapshot['alarm'], 'unknown')
        self.assertTrue(snapshot['smoke']['fresh'])
        self.assertFalse(snapshot['temperature']['fresh'])

    def test_active_alert_survives_staleness_and_disconnect(self):
        self.state.update('fire_alert', True)
        self.now += 20
        self.assertEqual(self.state.snapshot()['alarm'], 'active')
        self.state.disconnect()
        snapshot = self.state.snapshot()
        self.assertEqual(snapshot['alarm'], 'active')
        self.assertFalse(snapshot['fire_alert']['fresh'])
        json.dumps(snapshot, allow_nan=False)

    def test_reject_bad_data(self):
        for name, value in [('smoke', float('nan')), ('temperature', float('inf')),
                            ('fire_alert', 'false'), ('fire_alert', 1), ('smoke', True), ('other', 0)]:
            self.assertFalse(self.state.update(name, value))
        self.assertEqual(self.state.snapshot()['alarm'], 'unknown')

    def test_clear_after_new_valid_messages(self):
        for name, value in [('smoke', 2), ('temperature', -5), ('fire_alert', True)]:
            self.state.update(name, value)
        self.state.disconnect()
        self.state.update('fire_alert', False)
        self.assertEqual(self.state.snapshot()['alarm'], 'unknown')
        self.state.update('smoke', 0)
        self.state.update('temperature', 20)
        self.assertEqual(self.state.snapshot()['alarm'], 'clear')

    def test_state_endpoint(self):
        with patch.object(server, 'SENSORS', self.state):
            httpd = ThreadingHTTPServer(('127.0.0.1', 0), server.H)
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            try:
                with urllib.request.urlopen(f'http://127.0.0.1:{httpd.server_port}/state.json') as response:
                    data = json.load(response)
                self.assertEqual(data['sensors']['alarm'], 'unknown')
                self.assertIn('telemetry', data)
                self.assertIn('estop', data)
            finally:
                httpd.shutdown()
                httpd.server_close()
                thread.join()


if __name__ == '__main__':
    unittest.main()
