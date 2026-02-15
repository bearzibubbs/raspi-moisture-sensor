# Raspberry Pi Moisture Sensor Project

GPIO testing and moisture sensor scripts for **Raspberry Pi Zero 2 W** with **Grove Base HAT** and Grove moisture sensors.

**Compatible with Raspberry Pi OS Trixie (Debian 13)** and all Raspberry Pi models including Pi 5.

## Hardware

- **Raspberry Pi Zero 2 W**
- **Seeed Studio Grove Base HAT for Raspberry Pi**
- **Grove Moisture Sensor** (resistive type)
- **Grove Capacitive Moisture Sensor**

## Quick Start

### 1. Run Setup Script (on Raspberry Pi)

```bash
# Copy files to your Raspberry Pi, then:
cd raspi-moisture-sensor
chmod +x raspi-gpio-setup.sh
sudo ./raspi-gpio-setup.sh
sudo reboot
```

### 2. Connect Sensors

Connect your moisture sensors to the analog ports on the Grove Base HAT:

| Port | ADC Channel | Suggested Use |
|------|-------------|---------------|
| A0   | Channel 0   | First sensor  |
| A2   | Channel 2   | Second sensor |
| A4   | Channel 4   | Available     |
| A6   | Channel 6   | Available     |

### 3. Test Your Setup

```bash
# Verify I2C and Grove Base HAT connection
python3 gpio_pin_test.py scan

# Read all ADC channels
python3 gpio_pin_test.py adc

# Run all diagnostics
python3 gpio_pin_test.py all
```

### 4. Test Moisture Sensors

```bash
# Test resistive moisture sensor on channel 0
python3 test_grove_moisture.py 0

# Test capacitive moisture sensor on channel 2
python3 test_grove_capacitive.py 2
```

## Files

| File | Description |
|------|-------------|
| `raspi-gpio-setup.sh` | Installation script for all required software |
| `test_grove_moisture.py` | Test script for resistive moisture sensor |
| `test_grove_capacitive.py` | Test script for capacitive moisture sensor |
| `gpio_pin_test.py` | General GPIO testing utility |

## Software Installed by Setup Script

### System Packages
- `i2c-tools` - I2C debugging tools
- `gpiod` - GPIO character device tools
- `python3-dev` / `python3-pip` - Python development

### Python Libraries
- `gpiozero` - Modern GPIO library (recommended for all Raspberry Pi models)
- `lgpio` - Low-level GPIO backend for gpiozero
- `smbus2` - I2C communication
- `grove.py` - Seeed Studio Grove sensor library

## Sensor Calibration

Both sensors need calibration for accurate readings. Edit the `SENSOR_MIN` and `SENSOR_MAX` values in the test scripts:

### Resistive Sensor (test_grove_moisture.py)
```python
SENSOR_MIN = 0      # Value in dry air
SENSOR_MAX = 950    # Value in water
```

### Capacitive Sensor (test_grove_capacitive.py)
```python
SENSOR_MIN = 300    # Value in water (wet)
SENSOR_MAX = 800    # Value in dry air (dry)
```

**Note:** Capacitive sensors are inverted - lower values mean more moisture!

## Troubleshooting

### I2C Not Working
```bash
# Check if I2C is enabled
sudo raspi-config  # Interface Options > I2C > Enable

# Scan for devices (should see 0x04 or 0x08 for Grove Base HAT)
i2cdetect -y 1
```

### Sensors Not Reading
1. Verify Grove Base HAT is firmly seated on the GPIO header
2. Check sensor cable connections
3. Try a different analog port (A0, A2, A4, or A6)

### Permission Errors
```bash
# Add user to gpio and i2c groups
sudo usermod -aG gpio,i2c $USER
# Log out and back in
```

## Sensor Comparison

| Feature | Resistive Sensor | Capacitive Sensor |
|---------|-----------------|-------------------|
| Durability | Lower (probes corrode) | Higher (no exposed metal) |
| Long-term use | Weeks to months | Years |
| Response | Slightly faster | Slightly slower |
| Accuracy | Good | Good |
| Price | Lower | Higher |
| Best for | Short-term testing | Permanent installations |

## Next Steps

After verifying your sensors work:

1. **Data Logging** - Add timestamps and save readings to a file
2. **Web Dashboard** - Create a Flask/FastAPI server to view readings
3. **Alerts** - Send notifications when soil is too dry
4. **Automation** - Control a water pump based on moisture levels

## License

MIT License - Feel free to modify and use as needed.

## Resources

- [Grove Base HAT Wiki](https://wiki.seeedstudio.com/Grove_Base_Hat_for_Raspberry_Pi/)
- [Grove Moisture Sensor Wiki](https://wiki.seeedstudio.com/Grove-Moisture_Sensor/)
- [Grove Capacitive Moisture Sensor Wiki](https://wiki.seeedstudio.com/Grove-Capacitive_Moisture_Sensor-Corrosion-Resistant/)
- [grove.py GitHub](https://github.com/Seeed-Studio/grove.py)
