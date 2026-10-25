# SafeScout

A PuppyPi monitoring dashboard that combines sensor evidence with a recommended
operator response. It reports possible smoke or combustible-gas events, not a
confirmed fire, gas identity, or proof that an area is safe.

## Run the submission locally

Python 3 is sufficient; no ROS, hardware, API key, or packages are needed:

```bash
python3 demo.py
```

Open http://127.0.0.1:8088. In **Demo controls**, select **Normal**,
**Elevated reading**, then **Signal lost**. Signal lost stops updates and becomes
**Sensor offline** after three seconds. Select Normal to recover.

- Normal: “No elevated reading detected.”
- Alert: “Sensor reading above threshold.” Recommended action: Stop and inspect.
- Sensor offline: “Sensor data unavailable.” Recommended action: Stop and inspect.

The fixed pre-event baseline is the mean of 0.44, 0.45 and 0.46 V: **0.45 V**.
An increase of at least 25% triggers the demo alarm. Image evidence never changes
this baseline. Voltage is not presented as calibrated ppm.

## One dashboard, two input sources

```text
Demo voltages ──────────────┐
                           ├─ SensorState ─ reasoning.py ─ /state.json ─ dashboard
ROS smoke/camera/fault ─────┘                               recommendation
```

This integration preserves the sensor cache, ROS subscriber bridge, detector
package, and tests from `dashboard-smoke-alert`, plus the PCF8591 monitor from
`master`. Both `demo.py` and `server.py` expose `sensors` and `hazard` in the same
state response. The UI renders sensor freshness in Details and one main status,
explanation, and recommended action. Neither reasoning path dispatches commands.

- `sensor_state.py`: independent values, receipt timestamps, and stale detection.
- `reasoning.py`: fixed-baseline demo interpretation and ROS evidence adapter.
- `fire_sensors.py`: ROS subscriber callbacks forwarded to the portal.
- `server.py`: existing local/SSH bridge, camera proxy, voice, manual E-stop.
- `demo.py`: isolated localhost simulator; robot/voice POST routes return 403.
- `index.html`: compact camera/trend view, status, recent events and Details.
- `ros1_code_fire_detector/`: teammate's smoke/camera detector and tests.
- `gas-sensor/`: standalone MQ-2 / PCF8591 monitor from master.

The ROS adapter consumes `/smoke_detected`, `/camera_fire_detected`, `/fire_alert`,
and `/fire_sensor_fault`. It requires all four to be fresh; fault or missing data
never becomes Normal. Temperature is optional telemetry, not a requirement for
this smoke/camera configuration. An old active warning is retained in the
explanation during a fault. No baseline or calibrated concentration is invented
for raw ROS input. The demo's voltage threshold is not applied to arbitrary raw
values from the live bridge.

## What is simulated or not yet integrated

- Demo voltages and baseline samples are synthetic. No physical sensor is read.
- The selected SVG's hand-authored annotation supplies image context in Details.
  This is an explicitly labeled fallback, **not AI vision**. No callable Opus or
  other language-model integration was found in the repo; the external tmux voice
  bridge is not a model API and is not invoked by the demo.
- No project footage or photograph is included. Camera shows **No image available**
  in demo mode. The fixture selector remains in Details to demonstrate that image
  context changes the explanation without changing sensor calibration.
- The ROS camera detector is a color heuristic, not a trained model. Its candidate
  means a flame-colored region, not confirmed fire or measured temperature.
- All reasoning actions are recommendations. No robot commands or reports are sent.
  A manually controlled walking/stopping video illustrates the intended response.
- The PCF8591 monitor is retained but does not yet publish the ROS topics used by
  the bridge. A hardware driver/adapter is still needed before an end-to-end live
  MQ-2/PCF8591 demonstration. The optional GPIO reader is a different digital input.
- Live ROS/hardware operation has not been tested. Development and validation used
  local simulation and mocked sensor data only.

The trend keeps 60 distinct samples; the log keeps five status transitions in the
browser session. Both reset on reload. Calibration, interpreter information, and
prototype limitations are under Details. No footage is labeled live in demo mode.

## Tests

```bash
python3 -m unittest -v test_demo.py
python3 -m unittest discover -s tests -v
python3 -m unittest discover -s ros1_code_fire_detector/tests -v
node tests/dashboard.test.cjs
```

Validated: 20 Python tests pass; three synthetic camera tests skip when OpenCV/
NumPy are unavailable. Dashboard rendering and JavaScript syntax checks pass.
Tests cover both input paths, stale/fault data, optional temperature, fixed
calibration, image context, retained alerts, and disabled demo robot routes.

## Hardware portal (separate from the demo)

`server.py` is the original hardware entry point and may contact the robot. It was
not run during this work. See [ROS package instructions](ros1_code_fire_detector/README.md)
and [PCF8591 monitor instructions](gas-sensor/README.md) for the existing components.

Configuration includes `PUPPY_LOCAL`, `PUPPY_HOST`, `PORTAL_BIND`, `PORTAL_PORT`,
`PUPPY_CAM_TOPIC`, and optional `PORTAL_CERT` / `PORTAL_KEY` for HTTPS.
The sensor bridge supports `PUPPY_SMOKE_TOPIC`, `PUPPY_SMOKE_UNIT`,
`PUPPY_TEMPERATURE_TOPIC`, `PUPPY_TEMPERATURE_TYPE`, `PUPPY_FIRE_ALERT_TOPIC`,
`PUPPY_SMOKE_DETECTED_TOPIC`, `PUPPY_CAMERA_ALERT_TOPIC`,
`PUPPY_SENSOR_FAULT_TOPIC`, and `PORTAL_SENSOR_STALE_SECONDS` (default 10).
Only label a numeric smoke topic `V` if the publisher actually supplies volts.
The portal should stay on a private robot network or tailnet. Runtime files,
certificates, audio and logs belong in ignored `runtime/`.

Code style follows [PEP 8](https://peps.python.org/pep-0008/) and
[PEP 20](https://peps.python.org/pep-0020/): explicit logic, descriptive names,
and comments explaining decisions rather than restating code.
