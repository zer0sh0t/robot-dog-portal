# gas-sensor

MQ-2 gas sensor monitor for a Raspberry Pi via a **PCF8591** 8-bit I2C ADC
(default). An ADS1115 is also supported with `--ads`.

## Wiring
- MQ-2 `VCC` -> 5V, `GND` -> GND
- MQ-2 `AO` -> PCF8591 `AIN0`  (analog level)
- MQ-2 `DO` -> PCF8591 `AIN1`  (hardware threshold trip)
- PCF8591 `VCC` -> 5V, `GND` -> GND, `SDA`/`SCL` -> the board's I2C port (bus 1, addr 0x48)

## Run
```bash
sudo raspi-config         # Interface > I2C > on   (if not already)
python3 gas_monitor.py           # PCF8591 (no library needed, raw I2C)
python3 gas_monitor.py --ads     # if you swap in an ADS1115 instead
python3 gas_monitor.py --sim     # full logic on a synthetic signal, no hardware
```
The PCF8591 needs **no external library** - it's read over raw I2C at `0x48` on `/dev/i2c-1`.

## PCF8591 notes
- 8-bit: each channel reads **0-255**. The script scales to volts (`raw/255 * VREF`, VREF=5V).
- Read quirk: after selecting a channel you must **discard the first byte** (it's the
  previous conversion) and use the second. The script handles this.
- Address is fixed at `0x48`; it is NOT an ADS1115, so ignore ADS register/ADDR-pin advice.

## What it does
Parses the sensor as **change-from-baseline**, not an absolute value, and emits a
**state** every tick (logged to `gas_log.jsonl`):

- `WARMUP` heater settling (no alarms) · `OK` baseline air · `ELEVATED` real rise
- `ALARM` sustained rise (hysteresis + debounced) · `FAULT` dead/frozen/railed/I2C-error

The baseline only adapts while `OK`, so a slow leak can't drag it up and hide itself.
A dead or disagreeing sensor is a `FAULT`, never an "all clear". Tune via env vars
(top of `gas_monitor.py`): `GAS_T_HIGH`, `GAS_WARMUP_S`, `GAS_DEBOUNCE_N`, `GAS_VREF`, etc.
