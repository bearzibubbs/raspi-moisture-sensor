#!/usr/bin/env python3
"""
Moisture Sensor Calibration Helper

Guides you through calibrating moisture sensors and detecting their type.
Generates configuration that can be pushed to the orchestrator.

Usage:
    sudo python3 calibrate-sensors.py

Requirements:
    - Run as root (for I2C/SPI access)
    - Sensors physically connected to ADC
    - Water and dry environment for calibration
"""

import sys
import time
import json
from typing import Dict, List, Optional, Tuple


def banner():
    """Print welcome banner"""
    print("=" * 70)
    print("  MOISTURE SENSOR CALIBRATION HELPER")
    print("=" * 70)
    print()
    print("This tool will help you:")
    print("  1. Detect ADC hardware (Grove, ADS1115, or MCP3008)")
    print("  2. Choose which channel(s) to calibrate")
    print("  3. Calibrate each sensor (dry/wet readings, auto-detect type)")
    print("  4. Generate configuration for orchestrator")
    print()


def detect_adc() -> Tuple[str, object]:
    """
    Detect and initialize ADC hardware.

    Returns:
        (adc_type, adc_instance)
    """
    print("[1/5] Detecting ADC hardware...")
    print()

    # Try Grove Base HAT first (same as pi-agent uses)
    try:
        from grove.adc import ADC
        adc = ADC()
        # Test read channel 0 (Grove A0)
        val = adc.read(0)
        if val is not None:
            print("✓ Found Grove Base HAT ADC (grove.py)")
            print("  Analog channels: 0, 2, 4, 6 (A0, A2, A4, A6)")
            print()
            return ("Grove", adc)
    except Exception as e:
        print(f"  Grove ADC not found: {e}")

    # Try ADS1115 (I2C)
    try:
        import board
        import busio
        import adafruit_ads1x15.ads1115 as ADS
        from adafruit_ads1x15.analog_in import AnalogIn

        i2c = busio.I2C(board.SCL, board.SDA)
        ads = ADS.ADS1115(i2c)

        # Test read to verify it's working
        channel = AnalogIn(ads, ADS.P0)
        _ = channel.value

        print("✓ Found ADS1115 on I2C bus")
        print(f"  Address: 0x48 (default)")
        print()
        return ("ADS1115", ads)

    except Exception as e:
        print(f"  ADS1115 not found: {e}")

    # Try MCP3008 (SPI)
    try:
        import busio
        import digitalio
        import board
        import adafruit_mcp3xxx.mcp3008 as MCP
        from adafruit_mcp3xxx.analog_in import AnalogIn

        spi = busio.SPI(clock=board.SCK, MISO=board.MISO, MOSI=board.MOSI)
        cs = digitalio.DigitalInOut(board.D5)
        mcp = MCP.MCP3008(spi, cs)

        # Test read
        channel = AnalogIn(mcp, MCP.P0)
        _ = channel.value

        print("✓ Found MCP3008 on SPI bus")
        print()
        return ("MCP3008", mcp)

    except Exception as e:
        print(f"  MCP3008 not found: {e}")

    print()
    print("❌ ERROR: No ADC found!")
    print("   Make sure:")
    print("   - ADC is properly connected")
    print("   - I2C/SPI is enabled (raspi-config)")
    print("   - Required libraries are installed")
    sys.exit(1)


def read_channel(adc_type: str, adc, channel: int) -> Optional[int]:
    """
    Read a single channel from the ADC.

    Returns:
        Raw ADC value (0-1023 for Grove, 0-32767 for ADS1115, 0-1023 for MCP3008) or None
    """
    try:
        if adc_type == "Grove":
            # Grove Base HAT: channels 0, 2, 4, 6
            if channel not in (0, 2, 4, 6):
                return None
            return adc.read(channel)

        if adc_type == "ADS1115":
            import adafruit_ads1x15.ads1115 as ADS
            from adafruit_ads1x15.analog_in import AnalogIn

            channel_map = [ADS.P0, ADS.P1, ADS.P2, ADS.P3]
            if channel >= len(channel_map):
                return None

            analog_in = AnalogIn(adc, channel_map[channel])
            return analog_in.value

        elif adc_type == "MCP3008":
            import adafruit_mcp3xxx.mcp3008 as MCP
            from adafruit_mcp3xxx.analog_in import AnalogIn

            channel_map = [MCP.P0, MCP.P1, MCP.P2, MCP.P3,
                          MCP.P4, MCP.P5, MCP.P6, MCP.P7]
            if channel >= len(channel_map):
                return None

            analog_in = AnalogIn(adc, channel_map[channel])
            return analog_in.value

        else:
            return None

    except Exception as e:
        print(f"    Error reading channel {channel}: {e}")
        return None


def get_available_channels(adc_type: str) -> List[int]:
    """Return the list of valid channel numbers for this ADC type."""
    if adc_type == "Grove":
        return [0, 2, 4, 6]  # Grove Base HAT analog ports A0, A2, A4, A6
    if adc_type == "ADS1115":
        return list(range(4))
    return list(range(8))


def choose_channels(adc_type: str) -> List[int]:
    """
    Ask the user which channel(s) to calibrate (no auto-detection).

    Returns:
        Sorted list of channel numbers to calibrate
    """
    valid = get_available_channels(adc_type)
    print("[2/5] Choose channel(s) to calibrate")
    print()
    print(f"  Valid channels for {adc_type}: {valid}")
    if adc_type == "Grove":
        print("  (Grove Base HAT: 0=A0, 2=A2, 4=A4, 6=A6)")
    print()
    prompt = "  Enter channel(s), comma or space separated (e.g. 0, 2 or 0 2): "
    raw = input(prompt).strip()
    if not raw:
        print("  No channels entered. Exiting.")
        sys.exit(1)
    # Parse: allow "0, 2", "0 2", "0,2"
    parts = raw.replace(",", " ").split()
    chosen = []
    for p in parts:
        try:
            ch = int(p)
            if ch in valid:
                chosen.append(ch)
            else:
                print(f"  ⚠ Skipping {ch} (not in {valid})")
        except ValueError:
            print(f"  ⚠ Skipping '{p}' (not a number)")
    chosen = sorted(set(chosen))
    if not chosen:
        print("  No valid channels. Exiting.")
        sys.exit(1)
    print(f"  ✓ Will calibrate channel(s): {chosen}")
    print()
    return chosen


def calibrate_sensor(adc_type: str, adc, channel: int) -> Dict:
    """
    Calibrate a single sensor through interactive prompts.

    Returns:
        Configuration dict for this sensor
    """
    print("─" * 70)
    print(f"  CALIBRATING CHANNEL {channel}")
    print("─" * 70)
    print()

    # Step 1: Dry reading
    print("STEP 1: Dry Air Reading")
    print("  ➜ Remove sensor from soil")
    print("  ➜ Wipe sensor clean and dry")
    print("  ➜ Hold sensor in dry air")
    print()
    input("  Press ENTER when ready...")

    dry_readings = []
    print("  Taking readings", end="", flush=True)
    for _ in range(10):
        val = read_channel(adc_type, adc, channel)
        if val is not None:
            dry_readings.append(val)
        print(".", end="", flush=True)
        time.sleep(0.3)
    print(" done")

    dry_value = int(sum(dry_readings) / len(dry_readings))
    print(f"  ✓ Dry reading: {dry_value}")
    print()

    # Step 2: Wet reading
    print("STEP 2: Water Reading")
    print("  ➜ Place sensor in a glass of water")
    print("  ➜ Ensure sensor probes are fully submerged")
    print("  ➜ Wait a few seconds for reading to stabilize")
    print()
    input("  Press ENTER when ready...")

    wet_readings = []
    print("  Taking readings", end="", flush=True)
    for _ in range(10):
        val = read_channel(adc_type, adc, channel)
        if val is not None:
            wet_readings.append(val)
        print(".", end="", flush=True)
        time.sleep(0.3)
    print(" done")

    wet_value = int(sum(wet_readings) / len(wet_readings))
    print(f"  ✓ Wet reading: {wet_value}")
    print()

    # Step 3: Determine sensor type
    print("STEP 3: Detecting Sensor Type")
    print()

    if dry_value > wet_value:
        sensor_type = "capacitive"
        confidence = "HIGH"
        explanation = "Dry > Wet (inverted scale is typical of capacitive sensors)"
    else:
        sensor_type = "resistive"
        confidence = "HIGH"
        explanation = "Wet > Dry (normal scale is typical of resistive sensors)"

    # Check if difference is too small
    diff = abs(dry_value - wet_value)
    if diff < 100:
        confidence = "LOW"
        print(f"  ⚠ WARNING: Small difference between readings ({diff})")
        print(f"    This sensor may need better calibration or could be faulty")
        print()

    print(f"  Detected type: {sensor_type.upper()}")
    print(f"  Confidence: {confidence}")
    print(f"  Reason: {explanation}")
    print()

    # Confirm with user
    confirm = input(f"  Is this a {sensor_type} sensor? [Y/n]: ").strip().lower()
    if confirm and confirm != 'y':
        print()
        print("  What type is it?")
        print("    1. Capacitive")
        print("    2. Resistive")
        choice = input("  Enter 1 or 2: ").strip()
        sensor_type = "capacitive" if choice == "1" else "resistive"
        print(f"  ✓ Sensor type set to: {sensor_type}")

    print()

    # Step 4: Labels
    print("STEP 4: Sensor Labels")
    print()
    location = input("  Location (e.g., 'Greenhouse A'): ").strip() or "Unknown"
    plant_type = input("  Plant type (e.g., 'Tomato'): ").strip() or "Unknown"
    sensor_name = input("  Sensor name (e.g., 'Tomato-1'): ").strip() or f"Sensor-{channel}"
    print()

    # Build config
    config = {
        "channel": channel,
        "type": sensor_type,
        "calibration": {
            "min": min(dry_value, wet_value),
            "max": max(dry_value, wet_value)
        },
        "labels": {
            "location": location,
            "plant_type": plant_type,
            "sensor_name": sensor_name
        },
        "thresholds": {
            "dry_percent": 30,
            "wet_percent": 85,
            "hysteresis": 5
        }
    }

    print("  ✓ Calibration complete!")
    print()

    return config


def main():
    """Main calibration workflow"""
    banner()

    # Detect ADC
    adc_type, adc = detect_adc()

    # Choose which channels to calibrate (no auto-detect)
    channels = choose_channels(adc_type)

    # Calibrate each sensor
    print("[3/5] Calibrating sensors...")
    print()

    sensor_configs = []
    for i, channel in enumerate(channels):
        sensor_config = calibrate_sensor(adc_type, adc, channel)
        sensor_configs.append(sensor_config)

        if i < len(channels) - 1:
            print()
            input("Press ENTER to calibrate next sensor...")
            print()

    # Generate configuration
    print("=" * 70)
    print("[4/5] CALIBRATION SUMMARY")
    print("=" * 70)
    print()

    for config in sensor_configs:
        print(f"Channel {config['channel']}: {config['type'].upper()}")
        print(f"  Location: {config['labels']['location']}")
        print(f"  Plant: {config['labels']['plant_type']}")
        print(f"  Name: {config['labels']['sensor_name']}")
        print(f"  Range: {config['calibration']['min']} - {config['calibration']['max']}")
        print()

    # Generate orchestrator config
    orchestrator_config = {
        "sensors": sensor_configs
    }

    print("[5/5] ORCHESTRATOR CONFIGURATION")
    print("=" * 70)
    print()
    print("Copy this configuration and push to the orchestrator:")
    print()
    print("```json")
    print(json.dumps(orchestrator_config, indent=2))
    print("```")
    print()
    print("To apply this configuration to your agent:")
    print()
    print("  curl -X PUT https://orchestrator.example.com/agents/YOUR_AGENT_ID/config \\")
    print("    -H 'Content-Type: application/json' \\")
    print("    -d '" + json.dumps(orchestrator_config) + "'")
    print()

    # Save to file
    filename = f"sensor-config-{int(time.time())}.json"
    with open(filename, 'w') as f:
        json.dump(orchestrator_config, f, indent=2)

    print(f"✓ Configuration saved to: {filename}")
    print()
    print("=" * 70)
    print("  CALIBRATION COMPLETE!")
    print("=" * 70)
    print()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print()
        print()
        print("Calibration cancelled by user")
        sys.exit(1)
    except Exception as e:
        print()
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
