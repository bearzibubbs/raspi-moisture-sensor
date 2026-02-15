#!/usr/bin/env python3
"""
Grove Moisture Sensor Test Script (Resistive Type)
===================================================
Seeed Studio Grove Moisture Sensor

This script reads analog values from the resistive moisture sensor
connected to the Grove Base HAT on a Raspberry Pi.

Hardware Setup:
- Connect the Grove Moisture Sensor to an analog port (A0, A2, A4, or A6)
- The sensor uses two probes to measure soil resistance
- Wet soil = lower resistance = higher ADC value
- Dry soil = higher resistance = lower ADC value

Usage:
    python3 test_grove_moisture.py [channel]
    
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

def get_moisture_level(value, sensor_min=0, sensor_max=950):
    """
    Convert raw ADC value to moisture percentage.
    
    Typical values for Grove Moisture Sensor (resistive):
    - Dry air: ~0-100
    - Dry soil: ~100-300
    - Moist soil: ~300-700
    - Wet soil: ~700-950
    - In water: ~950+
    
    Note: Calibrate these values for your specific soil type!
    """
    percentage = ((value - sensor_min) / (sensor_max - sensor_min)) * 100
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
        from grove.grove_moisture_sensor import GroveMoistureSensor
        use_grove_lib = True
    except ImportError:
        try:
            from grove.adc import ADC
            use_grove_lib = False
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
    
    print("=" * 50)
    print(" Grove Moisture Sensor Test (Resistive)")
    print("=" * 50)
    print(f"Reading from ADC channel: {channel}")
    print("Press Ctrl+C to exit")
    print("-" * 50)
    
    # Initialize sensor
    if use_grove_lib:
        sensor = GroveMoistureSensor(channel)
    else:
        adc = ADC()
    
    # Calibration values (adjust these for your sensor/soil)
    SENSOR_MIN = 0      # Value in dry air
    SENSOR_MAX = 950    # Value in water
    
    print("\nCalibration values (edit script to adjust):")
    print(f"  Min (dry): {SENSOR_MIN}")
    print(f"  Max (wet): {SENSOR_MAX}")
    print("-" * 50)
    print()
    
    reading_count = 0
    
    while True:
        reading_count += 1
        
        # Read raw ADC value
        if use_grove_lib:
            raw_value = sensor.moisture
        else:
            raw_value = adc.read(channel)
        
        # Calculate percentage
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
