"""Thread-safe sensor cache. Freshness is measured with the portal's monotonic clock."""
import math
import threading
import time


class SensorState:
    def __init__(self, stale_after=10, smoke_unit="raw", clock=time.monotonic):
        if not math.isfinite(stale_after) or stale_after <= 0:
            raise ValueError("PORTAL_SENSOR_STALE_SECONDS must be positive and finite")
        self.stale_after = stale_after
        self.smoke_unit = smoke_unit
        self.clock = clock
        self.values = {}
        self.lock = threading.Lock()

    def update(self, name, value):
        if name not in ("smoke", "temperature", "fire_alert", "smoke_detected", "camera", "fire_sensor_fault"):
            return False
        if name in ("fire_alert", "smoke_detected", "camera", "fire_sensor_fault"):
            if type(value) is not bool:
                return False
        elif type(value) not in (int, float) or not math.isfinite(value):
            return False
        with self.lock:
            self.values[name] = (value, self.clock())
        return True

    def disconnect(self):
        # Preserve the last reading, especially an active alert, but invalidate freshness.
        with self.lock:
            self.values = {name: (value, float('-inf'))
                           for name, (value, _) in self.values.items()}

    def snapshot(self):
        with self.lock:
            now = self.clock()
            result = {}
            for name in ("smoke", "temperature", "fire_alert", "smoke_detected", "camera", "fire_sensor_fault"):
                value, received = self.values.get(name, (None, None))
                age = max(0, now - received) if received is not None else None
                result[name] = {"value": value,
                                "received_at": received if received is not None and math.isfinite(received) else None,
                                "age_s": round(age, 1) if age is not None and math.isfinite(age) else None,
                                "fresh": age is not None and age < self.stale_after}
            result["smoke"]["unit"] = self.smoke_unit
            result["temperature"]["unit"] = "°C"
            alert = result["fire_alert"]
            result["alarm"] = ("active" if alert["value"] is True else
                               "clear" if alert["fresh"] and all(result[n]["fresh"] for n in ("smoke", "temperature")) else
                               "unknown")
            return result

