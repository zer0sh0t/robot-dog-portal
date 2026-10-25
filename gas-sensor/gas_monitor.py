#!/usr/bin/env python3
"""
gas_monitor.py - MQ-2 gas sensor monitor (ADS1115: A0=AO analog, A1=DO digital).

Parses the sensor as CHANGE-FROM-BASELINE with fault awareness, not as an
absolute value. Emits a STATE, never a bare number:

  WARMUP   - heater still settling; no alarms yet
  OK       - air reads like the learned clean-air baseline
  ELEVATED - a real rise over baseline, below the alarm threshold
  ALARM    - sustained rise over the alarm threshold (debounced)
  FAULT    - sensor dead / disconnected / railed / I2C error
             (a fault is NEVER reported as "clear")

Each tick prints a line and appends one JSON object to gas_log.jsonl.

Run on the robot (real sensor):
    pip install adafruit-circuitpython-ads1x15
    sudo raspi-config  # Interface > I2C > on
    python3 gas_monitor.py

Try the logic with no hardware:
    python3 gas_monitor.py --sim      # synthetic signal: baseline -> leak -> clear
"""
import argparse, json, os, sys, time
from collections import deque

# ---- tunables (env-overridable) -------------------------------------------
RATE_HZ      = float(os.environ.get("GAS_RATE_HZ", "8"))     # samples/sec
WARMUP_S     = float(os.environ.get("GAS_WARMUP_S", "90"))   # heater settle, no alarms
EMA_ALPHA    = float(os.environ.get("GAS_EMA_ALPHA", "0.25"))# fast smoothing of AO
BASE_TAU_S   = float(os.environ.get("GAS_BASE_TAU_S", "120"))# baseline time-constant (slow)
T_ELEV       = float(os.environ.get("GAS_T_ELEV", "0.08"))   # +8%  over baseline = ELEVATED
T_HIGH       = float(os.environ.get("GAS_T_HIGH", "0.25"))   # +25% over baseline = alarm candidate
T_LOW        = float(os.environ.get("GAS_T_LOW", "0.12"))    # fall below +12% to clear (hysteresis)
DEBOUNCE_N   = int(os.environ.get("GAS_DEBOUNCE_N", "6"))    # consecutive hot samples to fire
DO_MID_V     = float(os.environ.get("GAS_DO_MID_V", "1.5"))  # DO < this = LOW = gas trip
RAIL_LO_V    = float(os.environ.get("GAS_RAIL_LO_V", "0.02"))# AO at/below = shorted/low rail
RAIL_HI_V    = float(os.environ.get("GAS_RAIL_HI_V", "4.98"))# AO at/above = high rail (8-bit max = 5.0V)
STUCK_WIN    = int(os.environ.get("GAS_STUCK_WIN", "120"))   # samples in the stuck-check window
I2C_BUS      = os.environ.get("GAS_I2C_BUS", "/dev/i2c-1")
I2C_ADDR     = int(os.environ.get("GAS_I2C_ADDR", "0x48"), 0)
VREF         = float(os.environ.get("GAS_VREF", "5.0"))      # PCF8591 reference (= its VCC)
LOGFILE      = os.environ.get("GAS_LOG", os.path.join(os.path.dirname(os.path.abspath(__file__)), "gas_log.jsonl"))


# ---- sensor back-ends ------------------------------------------------------
class PCF8591Sensor:
    """PCF8591 8-bit ADC (default). AIN0 = MQ-2 AO, AIN1 = MQ-2 DO.
    Pure stdlib raw I2C - no external libraries needed.
    Protocol: write the control byte to pick the channel, then read 2 bytes;
    the PCF8591's first byte is the PREVIOUS conversion (stale), so use the 2nd.
    Raw is 0-255; we scale to volts (raw/255*VREF) so the pipeline is uniform."""
    def __init__(self):
        import fcntl
        self._fd = os.open(I2C_BUS, os.O_RDWR)
        fcntl.ioctl(self._fd, 0x0703, I2C_ADDR)   # I2C_SLAVE

    def _ain(self, ch):
        os.write(self._fd, bytes([ch & 0x03]))    # control byte selects AIN0..3
        return os.read(self._fd, 2)[1]            # discard stale 1st byte

    def read(self):
        # may raise OSError on an I2C glitch; caller treats that as a fault
        ao = self._ain(0) / 255.0 * VREF
        do = self._ain(1) / 255.0 * VREF
        return ao, do


class AdsSensor:
    """ADS1115 16-bit ADC (--ads). A0 = MQ-2 AO, A1 = MQ-2 DO."""
    def __init__(self):
        import board, busio
        from adafruit_ads1x15.ads1115 import ADS1115
        from adafruit_ads1x15.analog_in import AnalogIn
        i2c = busio.I2C(board.SCL, board.SDA)
        ads = ADS1115(i2c)
        ads.gain = 2 / 3           # +/-6.144V range so a 0-5V signal never clips
        self._ao = AnalogIn(ads, 0)
        self._do = AnalogIn(ads, 1)

    def read(self):
        return self._ao.voltage, self._do.voltage


class SimSensor:
    """Synthetic AO/DO: clean baseline, a leak that ramps up then clears."""
    def __init__(self):
        self.t0 = time.time()

    def read(self):
        import math, random
        t = time.time() - self.t0
        base = 0.45 + 0.02 * math.sin(t / 30.0)        # slow wander
        leak = 0.0
        if 100 < t < 160:                               # a leak event
            leak = min(1.3, (t - 100) * 0.05)
        ao = base + leak + random.uniform(-0.004, 0.004)
        do = 0.2 if leak > 0.6 else 3.3                 # hardware trip when strong
        return max(0.0, ao), do


# ---- the monitor -----------------------------------------------------------
def run(sensor, once=False):
    period = 1.0 / RATE_HZ
    base_alpha = 1.0 - pow(2.718281828, -period / BASE_TAU_S)  # EMA alpha for the slow baseline
    ao_ema = None
    baseline = None
    state = "WARMUP"
    hot = 0                       # consecutive alarm-candidate samples
    disagree = 0                  # consecutive DO/AO disagreements
    recent = deque(maxlen=STUCK_WIN)
    start = time.time()

    while True:
        ts = time.time()
        # --- read + hard faults ---------------------------------------------
        try:
            ao_v, do_v = sensor.read()
        except Exception as e:
            emit(ts, None, None, None, None, None, None, "FAULT", note=f"read error: {e}")
            if once:
                return
            time.sleep(period)
            continue

        ao_ema = ao_v if ao_ema is None else EMA_ALPHA * ao_v + (1 - EMA_ALPHA) * ao_ema
        recent.append(ao_v)
        do_trip = do_v < DO_MID_V
        warming = (ts - start) < WARMUP_S

        fault = None
        if ao_v <= RAIL_LO_V:
            fault = "AO railed low (shorted/disconnected)"
        elif ao_v >= RAIL_HI_V:
            fault = "AO railed high (wiring)"
        elif not warming and len(recent) >= STUCK_WIN and max(recent) == min(recent):
            fault = "AO frozen (dead/disconnected sensor)"

        # --- state machine ---------------------------------------------------
        dev = None
        if fault:
            state = "FAULT"
        elif warming:
            state = "WARMUP"
        else:
            if baseline is None:
                baseline = ao_ema            # lock baseline the first clean sample after warmup
            dev = (ao_ema - baseline) / baseline if baseline > 1e-6 else 0.0

            # hysteresis + debounce on the alarm band
            if dev >= T_HIGH:
                hot += 1
            elif dev <= T_LOW:
                hot = 0
            # (between T_LOW and T_HIGH: hold the counter, don't grow it)

            if hot >= DEBOUNCE_N:
                state = "ALARM"
            elif dev >= T_ELEV:
                state = "ELEVATED"
            elif dev <= T_LOW:
                state = "OK"
            # else: keep previous state in the dead-band

            # cross-check the hardware trip against the analog read
            analog_hot = dev >= T_ELEV
            disagree = disagree + 1 if (do_trip != analog_hot) else 0
            note = "DO/AO disagree" if disagree >= DEBOUNCE_N else ""

            # adapt the baseline ONLY while genuinely OK, so a slow leak
            # can't quietly drag the baseline up and hide itself
            if state == "OK" and not do_trip:
                baseline += base_alpha * (ao_ema - baseline)

            emit(ts, ao_v, ao_ema, baseline, dev, do_v, do_trip, state, note=note)
            if once:
                return
            time.sleep(period)
            continue

        emit(ts, ao_v, ao_ema, baseline, dev, do_v, do_trip, state)
        if once:
            return
        time.sleep(period)


def _std(vals):
    n = len(vals)
    if n < 2:
        return 1.0
    m = sum(vals) / n
    return (sum((v - m) ** 2 for v in vals) / n) ** 0.5


def emit(ts, ao_v, ao_ema, baseline, dev, do_v, do_trip, state, note=""):
    rec = {
        "ts": round(ts, 3),
        "ao_v": _r(ao_v), "ao_ema": _r(ao_ema), "baseline": _r(baseline),
        "dev_pct": (round(dev * 100, 1) if dev is not None else None),
        "do_v": _r(do_v), "do_trip": do_trip, "state": state,
    }
    if note:
        rec["note"] = note
    try:
        with open(LOGFILE, "a") as f:
            f.write(json.dumps(rec) + "\n")
    except Exception:
        pass
    dv = f"{rec['dev_pct']:+.1f}%" if rec["dev_pct"] is not None else "  -  "
    av = f"{ao_v:.3f}V" if ao_v is not None else "  --  "
    do_s = ("TRIP" if do_trip else "off ") if do_trip is not None else "--"
    print(f"{time.strftime('%H:%M:%S')}  AO={av}  dev={dv:>7}  DO={do_s}  [{state}]"
          + (f"  ({note})" if note else ""), flush=True)


def _r(x):
    return round(x, 4) if isinstance(x, (int, float)) else None


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--sim", action="store_true", help="synthetic signal, no hardware")
    ap.add_argument("--ads", action="store_true", help="use an ADS1115 instead of the default PCF8591")
    ap.add_argument("--once", action="store_true", help="single reading then exit (for tests)")
    a = ap.parse_args()
    if a.sim:
        print("[sim mode] synthetic MQ-2 signal; leak event around t=100-160s", flush=True)
        run(SimSensor(), once=a.once)
    else:
        try:
            s = AdsSensor() if a.ads else PCF8591Sensor()
        except Exception as e:
            chip = "ADS1115" if a.ads else "PCF8591"
            print(f"{chip} not available ({e}).\n"
                  f"Enable I2C: sudo raspi-config > Interface > I2C > on\n"
                  f"PCF8591 needs no library (raw I2C at 0x48 on /dev/i2c-1).\n"
                  f"Test the logic with:  python3 gas_monitor.py --sim", file=sys.stderr)
            sys.exit(1)
        print(f"[{'ADS1115' if a.ads else 'PCF8591'}] reading {I2C_BUS} @ {hex(I2C_ADDR)}", flush=True)
        run(s, once=a.once)

