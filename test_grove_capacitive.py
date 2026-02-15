#!/usr/bin/env python3
"""
Grove Capacitive Moisture Sensor Test Script
=============================================
Seeed Studio Grove Capacitive Moisture Sensor

This script reads analog values from the capacitive moisture sensor
connected to the Grove Base HAT on a Raspberry Pi.

Key Differences from Resistive Sensor:
- No exposed metal probes = no corrosion over time
- Better for long-term soil monitoring
- More consistent readings in varying soil conditions
- Slightly different value range than resistive sensors

Hardware Setup:
- Connect the Grove Capacitive Moisture Sensor to an analog port (A0, A2, A4, or A6)
- The sensor measures capacitance changes due to moisture
- Wet soil = higher capacitance = LOWER ADC value (inverted!)
- Dry soil = lower capacitance = HIGHER ADC value

Usage:
    python3 test_grove_capacitive.py [channel]
    
    channel: 0-7 (default: 0 for port A0)
             0=A0, 2=A2, 4=A4, 6=A6 for standard Grove ports
"""

import sys
import time
import signal

# Graceful exit handler
def signal_handler(sig, frame):
    print("\n\nExiting... Goodbye! 🌱")
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

def get_moisture_level(value, sensor_min=300, sensor_max=800):
    """
    Convert raw ADC value to moisture percentage.
    
    NOTE: Capacitive sensors are INVERTED compared to resistive!
    - Higher ADC value = DRY
    - Lower ADC value = WET
    
    Typical values for Grove Capacitive Moisture Sensor:
    - In water: ~300-350
    - Wet soil: ~350-450
    - Moist soil: ~450-550
    - Dry soil: ~550-700
    - Dry air: ~700-800+
    
    These values can vary significantly - calibrate for your sensor!
    """
    # Invert the calculation since capacitive sensors work opposite
    percentage = ((sensor_max - value) / (sensor_max - sensor_min)) * 100
    return max(0, min(100, percentage))

def get_moisture_status(percentage):
    """Return a human-readable moisture status."""
    if percentage < 20:
        return "🏜️  Very Dry - Water immediately!"
    elif percentage < 40:
        return "🌵 Dry - Needs watering"
    elif percentage < 60:
        return "🌿 Moist - Good condition"
    elif percentage < 80:
        return "💧 Wet - Well watered"
    else:
        return "🌊 Very Wet - Reduce watering"

def main():
    # Try to import grove library
    try:
        from grove.adc import ADC
    except ImportError:
        print("Error: grove.py library not found!")
        print("Please run the setup script first: sudo ./raspi-gpio-setup.sh")
        sys.exit(1)
    
    # Get channel from command line argument
    channel = 0
    if len(sys.argv) > 1:
        try:
            channel = int(sys.argv[1])
            if channel not in range(8):
                raise ValueError
        except ValueError:
            print(f"Invalid channel: {sys.argv[1]}")
            print("Channel must be 0-7 (use 0, 2, 4, or 6 for Grove ports)")
            sys.exit(1)
    
    print("=" * 55)
    print(" Grove Capacitive Moisture Sensor Test")
    print("=" * 55)
    print(f"Reading from ADC channel: {channel}")
    print("Press Ctrl+C to exit")
    print("-" * 55)
    
    # Initialize ADC
    adc = ADC()
    
    # Calibration values (adjust these for your sensor/soil)
    # NOTE: For capacitive sensors, MIN is WET and MAX is DRY!
    SENSOR_MIN = 400    # Value in water (wet)
    SENSOR_MAX = 800    # Value in dry air (dry)
    
    print("\nCalibration values (edit script to adjust):")
    print(f"  Min (wet/water): {SENSOR_MIN}")
    print(f"  Max (dry/air):   {SENSOR_MAX}")
    print()
    print("⚠️  Note: Capacitive sensors are INVERTED!")
    print("   Lower raw value = MORE moisture")
    print("-" * 55)
    print()
    
    # Calibration mode helper
    print("TIP: To calibrate your sensor:")
    print("  1. Note the raw value in dry air (set as SENSOR_MAX)")
    print("  2. Note the raw value in water (set as SENSOR_MIN)")
    print("-" * 55)
    print()
    
    reading_count = 0
    
    while True:
        reading_count += 1
        
        # Read raw ADC value
        raw_value = adc.read(channel)
        
        # Calculate percentage (inverted for capacitive sensor)
        percentage = get_moisture_level(raw_value, SENSOR_MIN, SENSOR_MAX)
        status = get_moisture_status(percentage)
        
        # Create visual bar
        bar_length = 30
        filled = int(bar_length * percentage / 100)
        bar = "█" * filled + "░" * (bar_length - filled)
        
        # Print reading
        print(f"[{reading_count:04d}] Raw: {raw_value:4d} | {percentage:5.1f}% [{bar}] {status}")
        
        time.sleep(1)

if __name__ == "__main__":
    main()
