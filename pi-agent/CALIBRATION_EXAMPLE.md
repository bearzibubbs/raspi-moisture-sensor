# Calibration Helper - Example Session

Here's what the calibration process looks like:

```
======================================================================
  MOISTURE SENSOR CALIBRATION HELPER
======================================================================

This tool will help you:
  1. Detect which ADC channels have sensors connected
  2. Calibrate each sensor (dry/wet readings)
  3. Auto-detect sensor type (capacitive vs resistive)
  4. Generate configuration for orchestrator

[1/5] Detecting ADC hardware...

✓ Found ADS1115 on I2C bus
  Address: 0x48 (default)

[2/5] Scanning for connected sensors...

  Channel 0: ✓ Sensor detected (avg: 650)
  Channel 1: No signal
  Channel 2: ✓ Sensor detected (avg: 420)
  Channel 3: No sensor (floating pin, avg: 28)

✓ Found 2 sensor(s) on channel(s): [0, 2]

[3/5] Calibrating sensors...

──────────────────────────────────────────────────────────────────────
  CALIBRATING CHANNEL 0
──────────────────────────────────────────────────────────────────────

STEP 1: Dry Air Reading
  ➜ Remove sensor from soil
  ➜ Wipe sensor clean and dry
  ➜ Hold sensor in dry air

  Press ENTER when ready...
  Taking readings.......... done
  ✓ Dry reading: 782

STEP 2: Water Reading
  ➜ Place sensor in a glass of water
  ➜ Ensure sensor probes are fully submerged
  ➜ Wait a few seconds for reading to stabilize

  Press ENTER when ready...
  Taking readings.......... done
  ✓ Wet reading: 312

STEP 3: Detecting Sensor Type

  Detected type: CAPACITIVE
  Confidence: HIGH
  Reason: Dry > Wet (inverted scale is typical of capacitive sensors)

  Is this a capacitive sensor? [Y/n]: y

STEP 4: Sensor Labels

  Location (e.g., 'Greenhouse A'): Greenhouse A
  Plant type (e.g., 'Tomato'): Tomato
  Sensor name (e.g., 'Tomato-1'): Tomato-1

  ✓ Calibration complete!

Press ENTER to calibrate next sensor...

──────────────────────────────────────────────────────────────────────
  CALIBRATING CHANNEL 2
──────────────────────────────────────────────────────────────────────

STEP 1: Dry Air Reading
  ➜ Remove sensor from soil
  ➜ Wipe sensor clean and dry
  ➜ Hold sensor in dry air

  Press ENTER when ready...
  Taking readings.......... done
  ✓ Dry reading: 156

STEP 2: Water Reading
  ➜ Place sensor in a glass of water
  ➜ Ensure sensor probes are fully submerged
  ➜ Wait a few seconds for reading to stabilize

  Press ENTER when ready...
  Taking readings.......... done
  ✓ Wet reading: 892

STEP 3: Detecting Sensor Type

  Detected type: RESISTIVE
  Confidence: HIGH
  Reason: Wet > Dry (normal scale is typical of resistive sensors)

  Is this a resistive sensor? [Y/n]: y

STEP 4: Sensor Labels

  Location (e.g., 'Greenhouse A'): Greenhouse B
  Plant type (e.g., 'Tomato'): Basil
  Sensor name (e.g., 'Tomato-1'): Basil-1

  ✓ Calibration complete!

======================================================================
[4/5] CALIBRATION SUMMARY
======================================================================

Channel 0: CAPACITIVE
  Location: Greenhouse A
  Plant: Tomato
  Name: Tomato-1
  Range: 312 - 782

Channel 2: RESISTIVE
  Location: Greenhouse B
  Plant: Basil
  Name: Basil-1
  Range: 156 - 892

[5/5] ORCHESTRATOR CONFIGURATION
======================================================================

Copy this configuration and push to the orchestrator:

```json
{
  "sensors": [
    {
      "channel": 0,
      "type": "capacitive",
      "calibration": {
        "min": 312,
        "max": 782
      },
      "labels": {
        "location": "Greenhouse A",
        "plant_type": "Tomato",
        "sensor_name": "Tomato-1"
      },
      "thresholds": {
        "dry_percent": 30,
        "wet_percent": 85,
        "hysteresis": 5
      }
    },
    {
      "channel": 2,
      "type": "resistive",
      "calibration": {
        "min": 156,
        "max": 892
      },
      "labels": {
        "location": "Greenhouse B",
        "plant_type": "Basil",
        "sensor_name": "Basil-1"
      },
      "thresholds": {
        "dry_percent": 30,
        "wet_percent": 85,
        "hysteresis": 5
      }
    }
  ]
}
```

To apply this configuration to your agent:

  curl -X PUT https://orchestrator.example.com/agents/pi-greenhouse-01/config \
    -H 'Content-Type: application/json' \
    -d '{"sensors":[{"channel":0,"type":"capacitive",...}]}'

✓ Configuration saved to: sensor-config-1708129847.json

======================================================================
  CALIBRATION COMPLETE!
======================================================================
```

## Key Features

1. **Auto-detects ADC hardware** (ADS1115 or MCP3008)
2. **Scans all channels** to find connected sensors
3. **Interactive calibration** guides you through dry/wet readings
4. **Smart type detection** based on reading patterns
5. **User confirmation** - you can override auto-detection
6. **Generates JSON config** ready to push to orchestrator
7. **Saves to file** for later reference

## Detection Logic

**Capacitive Sensors:**
- Dry reading > Wet reading (inverted scale)
- Typically higher baseline values
- Example: Dry=782, Wet=312

**Resistive Sensors:**
- Wet reading > Dry reading (normal scale)
- Wide range of values
- Example: Dry=156, Wet=892

**Low Confidence Warning:**
- If dry/wet difference < 100
- Suggests sensor may be faulty or needs recalibration
