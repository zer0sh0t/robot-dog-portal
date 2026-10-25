import json
import threading
import time
import unittest
import urllib.error
import urllib.request

import demo


class RulesTest(unittest.TestCase):
    def test_baseline_threshold_and_missing(self):
        for value in demo.BASELINE_SAMPLES:
            self.assertEqual(demo.interpret(value, 10, 10, 'clear')['status'], 'OK')
        self.assertEqual(demo.interpret(0.57, 10, 10, 'clear')['status'], 'ALARM')
        for value, stamp in ((None, None), (0.45, None), (0.45, 0), (0.68, 0)):
            result = demo.interpret(value, stamp, 10, 'clear')
            self.assertEqual(result['status'], 'FAULT')
            self.assertEqual(result['message'], 'Sensor data unavailable.')

    def test_image_changes_context_not_calibration(self):
        clear = demo.interpret(0.66, 10, 10, 'clear')
        smoke = demo.interpret(0.66, 10, 10, 'smoke')
        self.assertNotEqual(clear['explanation'], smoke['explanation'])
        for key in ('baseline_v', 'threshold_v', 'status', 'proposed_action'):
            self.assertEqual(clear[key], smoke[key])
        self.assertEqual(demo.interpret(0.45, 10, 10, 'smoke')['proposed_action'], 'MONITOR_AND_REPORT')


class CompleteFlowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = demo.DemoServer(0)
        cls.url = 'http://127.0.0.1:' + str(cls.server.server_port)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def request(self, path, data=None):
        req = urllib.request.Request(self.url + path, data=None if data is None else json.dumps(data).encode(), headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req) as response:
            return response.read()

    def test_complete_flow(self):
        self.assertIn(b'id="scout"', self.request('/'))
        self.assertTrue(self.request('/camstream').startswith(b'\x89PNG'))
        ok = json.loads(self.request('/demo', {'scenario': 'OK', 'image': 'clear'}))['hazard']
        self.assertEqual(ok['message'], 'No elevated reading detected.')
        self.assertEqual(ok['status'], 'OK')
        alarm = json.loads(self.request('/demo', {'scenario': 'ALARM', 'image': 'smoke'}))['hazard']
        self.assertEqual(alarm['status'], 'ALARM')
        self.assertEqual(alarm['proposed_action'], 'STOP_AND_REPORT')
        self.assertIn('possible smoke', alarm['explanation'])
        self.assertTrue(self.request(alarm['image_url']).startswith(b'\x89PNG'))
        clear = json.loads(self.request('/demo', {'image': 'clear'}))['hazard']
        self.assertNotEqual(alarm['explanation'], clear['explanation'])
        self.request('/demo', {'scenario': 'FAULT'})
        time.sleep(demo.STALE_SECONDS + 0.15)
        fault = json.loads(self.request('/state.json'))['hazard']
        self.assertEqual(fault['status'], 'FAULT')
        self.assertEqual(fault['message'], 'Sensor data unavailable.')
        self.assertEqual(fault['proposed_action'], 'STOP_AND_REPORT')
        for result in (ok, alarm, fault):
            self.assertEqual(result['baseline_v'], 0.45)
            self.assertFalse(result['action_executed'])
        recovered = json.loads(self.request('/demo', {'scenario': 'OK'}))['hazard']
        self.assertEqual(recovered['status'], 'OK')

    def test_robot_routes_blocked(self):
        for path in ('/estop', '/estop/clear', '/heard', '/speak_test'):
            with self.assertRaises(urllib.error.HTTPError) as error:
                self.request(path, {})
            self.assertEqual(error.exception.code, 403)


if __name__ == '__main__':
    unittest.main(verbosity=2)
