# gas-sensor

MQ-2 gas sensor monitor for the Raspberry Pi via an ADS1115 ADC.

## Wiring
- MQ-2 `VCC` -> 5V, `GND` -> GND
- MQ-2 `AO` -> ADS1115 `A0`  (analog level)
- MQ-2 `DO` -> ADS1115 `A1`  (hardware threshold trip; reading it through the ADC avoids a 5V->3.3V divider)
- ADS1115 `VCC` -> 5V, `GND` -> GND, `SDA`/`SCL` -> the board's I2C port

## Run
```bash
pip install adafruit-circuitpython-ads1x15
sudo raspi-config         # Interface > I2C > on
i2cdetect -y 1            # expect 0x48
python3 gas_monitor.py
```
No hardware? `python3 gas_monitor.py --sim` runs the full logic on a synthetic signal.

## What it does
Parses the sensor as **change-from-baseline**, not an absolute value, and emits a
**state** every tick (logged to `gas_log.jsonl`):

- `WARMUP` heater settling (no alarms) · `OK` baseline air · `ELEVATED` real rise
- `ALARM` sustained rise (hysteresis + debounced) · `FAULT` dead/disconnected/railed/I2C-error

The baseline only adapts while `OK`, so a slow leak can't drag it up and hide itself.
A dead or disagreeing sensor is a `FAULT`, never an "all clear". Tune via env vars
(see the top of `gas_monitor.py`): `GAS_T_HIGH`, `GAS_WARMUP_S`, `GAS_DEBOUNCE_N`, etc.
