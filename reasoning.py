"""Shared hazard interpretation for the demo and the portal sensor bridge."""

import time
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BASELINE_SAMPLES = (0.44, 0.45, 0.46)
ALARM_SAMPLES = (0.66, 0.68, 0.67)
BASELINE = sum(BASELINE_SAMPLES) / len(BASELINE_SAMPLES)
ALARM_RISE = 0.25
STALE_SECONDS = 3.0
SAMPLE_INTERVAL = 0.5
SCENARIOS = ("OK", "ALARM", "FAULT")
IMAGES = ("clear", "smoke")


def image_evidence(image_name):
    """Read the hand-written annotation, not a vision model prediction."""
    image = ROOT / "demo-assets" / f"{image_name}.svg"
    return ET.parse(image).find("{http://www.w3.org/2000/svg}desc").text


def interpret(reading, updated_at, now, image_name):
    age = None if updated_at is None else max(0, now - updated_at)
    deviation = None if reading is None else (reading - BASELINE) / BASELINE

    # Freshness takes priority: a stale low reading must not report OK.
    if reading is None or age is None or age > STALE_SECONDS:
        status = "FAULT"
        message = "Sensor data unavailable."
        explanation = (
            f"No fresh sensor update within {STALE_SECONDS:g} seconds. "
            "Image evidence cannot replace sensor data."
        )
        action = "STOP_AND_REPORT"
    elif deviation >= ALARM_RISE:
        status = "ALARM"
        message = "Possible smoke or combustible-gas event."
        explanation = (
            f"Reading is {deviation:.1%} above the fixed baseline; "
            f"threshold is +{ALARM_RISE:.0%}. "
            "The MQ-2 cannot identify a specific gas."
        )
        action = "STOP_AND_REPORT"
    else:
        status = "OK"
        message = "No elevated reading detected."
        explanation = (
            f"Reading is {deviation:.1%} from the fixed baseline. "
            "This is a sensor status, not proof that the area is safe."
        )
        action = "MONITOR_AND_REPORT" if image_name == "smoke" else "MONITOR"

    explanation += (
        f" Image fixture: {image_evidence(image_name)} "
        "An ordinary camera cannot measure temperature."
    )
    return {
        "status": status,
        "message": message,
        "explanation": explanation,
        "proposed_action": action,
        "action_executed": False,
        "interpreter": "Fallback: rules + image fixture annotation (no AI vision)",
        "reading_v": reading,
        "baseline_v": round(BASELINE, 3),
        "threshold_v": round(BASELINE * (1 + ALARM_RISE), 4),
        "age_s": None if age is None else round(age, 1),
        "sample_id": updated_at,
        "image_url": f"/demo-assets/{image_name}-scene.png",
    }



def from_sensors(sensors):
    """Interpret reported detector signals without inventing calibration."""
    alert = sensors.get("fire_alert", {})
    fault = sensors.get("fire_sensor_fault", {})
    camera = sensors.get("camera", {})
    smoke = sensors.get("smoke_detected", {})
    voltage = sensors.get("smoke", {})
    complete = all(item.get("fresh") for item in (alert, fault, camera, smoke))
    offline = not complete or fault.get("value") is not False
    # Retain an active warning in the explanation even when its source goes stale.
    possible_hazard = any(item.get("value") is True for item in (alert, camera, smoke))
    if offline:
        status, message = "FAULT", "Sensor data unavailable."
    elif possible_hazard:
        status, message = "ALARM", "Possible smoke or combustible-gas event."
    else:
        status, message = "OK", "No elevated reading detected."
    evidence = []
    if smoke.get("value") is True:
        evidence.append("Smoke comparator reported an elevated reading.")
    if camera.get("value") is True:
        evidence.append("Camera reported a flame-colored region; this is an unconfirmed color heuristic.")
    if alert.get("value") is True:
        evidence.append("Detector reported a possible hazard.")
    if offline:
        evidence.append("Required detector data is missing, stale, or faulted.")
    has_voltage = voltage.get("fresh") and voltage.get("unit") == "V"
    return {
        "status": status, "message": message,
        "explanation": " ".join(evidence) or "Fresh detector signals report no candidate hazard; this does not prove safety.",
        "proposed_action": "STOP_AND_REPORT" if offline or possible_hazard else "MONITOR",
        "action_executed": False,
        "interpreter": "Rules over ROS smoke, camera, alarm, and fault signals; no connected language model.",
        "reading_v": voltage.get("value") if has_voltage else None,
        "baseline_v": None, "threshold_v": None,
        "age_s": max((item.get("age_s") or 0 for item in (alert, fault, camera, smoke)), default=0) if complete else None,
        "sample_id": None, "image_url": None,
    }
