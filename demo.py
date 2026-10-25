#!/usr/bin/env python3
"""Run the SafeScout dashboard with synthetic inputs on localhost."""

import argparse
import json
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

from reasoning import (
    ROOT, BASELINE_SAMPLES, ALARM_SAMPLES, BASELINE, ALARM_RISE,
    STALE_SECONDS, SAMPLE_INTERVAL, SCENARIOS, IMAGES, interpret,
)
from sensor_state import SensorState


class Demo:
    def __init__(self):
        self.scenario = "OK"
        self.image = "clear"
        self.reading = BASELINE
        self.updated_at = time.monotonic()
        self.sequence = 0
        self.sensors = SensorState(stale_after=STALE_SECONDS, smoke_unit="V")
        self.sensors.update("smoke", self.reading)

    def configure(self, data):
        if not isinstance(data, dict):
            raise ValueError("Expected a JSON object")
        scenario = data.get("scenario", self.scenario)
        image = data.get("image", self.image)
        if scenario not in SCENARIOS or image not in IMAGES:
            raise ValueError("Invalid scenario or image")

        self.scenario = scenario
        self.image = image
        if scenario != "FAULT":
            self.updated_at = time.monotonic() - SAMPLE_INTERVAL

    def state(self):
        now = time.monotonic()
        # Sampling is driven by dashboard polls. FAULT stops advancing the clock.
        if self.scenario != "FAULT" and now - self.updated_at >= SAMPLE_INTERVAL:
            samples = ALARM_SAMPLES if self.scenario == "ALARM" else BASELINE_SAMPLES
            self.reading = samples[self.sequence % len(samples)]
            self.sequence += 1
            self.updated_at = now
            self.sensors.update("smoke", self.reading)

        sensors = self.sensors.snapshot()
        reading = sensors["smoke"]
        hazard = interpret(reading["value"], reading["received_at"], now, self.image)
        return {
            "demo": True,
            "sensors": sensors,
            "hazard": hazard,
            "scenario": self.scenario,
            "estop": False,
            "telemetry": {"online": False, "battery_v": None},
            "say": [],
            "feed": [{
                "ts": time.time(),
                "kind": "info",
                "text": (
                    "Demo only: synthetic sensor, annotated sample image, "
                    "proposed actions never dispatched."
                ),
            }],
        }


class DemoServer(HTTPServer):
    def __init__(self, port):
        super().__init__(("127.0.0.1", port), Handler)
        self.demo = Demo()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send(self, code, content_type, body):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, code, data):
        self.send(code, "application/json", json.dumps(data))

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/state.json":
            self.send_json(200, self.server.demo.state())
        elif path in ("/", "/index.html"):
            self.send(200, "text/html", (ROOT / "index.html").read_bytes())
        elif path == "/camstream":
            image = ROOT / "demo-assets" / f"{self.server.demo.image}-scene.png"
            self.send(200, "image/png", image.read_bytes())
        elif path in ("/demo-assets/clear-scene.png", "/demo-assets/smoke-scene.png"):
            self.send(200, "image/png", (ROOT / path.lstrip("/")).read_bytes())
        elif path in ("/demo-assets/clear.svg", "/demo-assets/smoke.svg"):
            self.send(200, "image/svg+xml", (ROOT / path.lstrip("/")).read_bytes())
        else:
            self.send(404, "text/plain", "Not found")

    def do_POST(self):
        # The live portal's robot and voice routes are intentionally absent.
        if self.path != "/demo":
            self.send_json(403, {
                "error": "Robot and voice actions disabled in demo mode."
            })
            return

        try:
            length = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(length))
            self.server.demo.configure(data)
        except (ValueError, TypeError):
            self.send_json(400, {"error": "Invalid demo input"})
            return

        self.send_json(200, self.server.demo.state())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8088)
    args = parser.parse_args()
    with DemoServer(args.port) as server:
        print(
            f"SafeScout DEMO: http://127.0.0.1:{server.server_port} "
            "(no robot connection)",
            flush=True,
        )
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
