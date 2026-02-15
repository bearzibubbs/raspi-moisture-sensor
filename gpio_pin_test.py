#!/usr/bin/env python3
"""
GPIO Pin Testing Utility for Raspberry Pi
==========================================
A comprehensive tool for testing GPIO pins and I2C connectivity
on a Raspberry Pi with Grove Base HAT.

Features:
- Scan I2C bus for connected devices
- Test individual GPIO pins (input/output)
- Display GPIO pinout information
- Verify Grove Base HAT connection
- Read all ADC channels

Usage:
    python3 gpio_pin_test.py [command]
    
Commands:
    scan     - Scan I2C bus for devices (default)
    pinout   - Show GPIO pinout information
    adc      - Read all ADC channels
    gpio     - Interactive GPIO pin test
    all      - Run all tests
"""

import sys
import time
import subprocess

def print_header(title):
    """Print a formatted header."""
    print()
    print("=" * 60)
    print(f" {title}")
    print("=" * 60)

def print_section(title):
    """Print a section divider."""
    print()
    print(f"--- {title} ---")

def scan_i2c():
    """Scan I2C bus for connected devices."""
    print_header("I2C Bus Scan")
    
    print("\nScanning I2C bus 1 for devices...")
    print("(Grove Base HAT typically appears at 0x04 or 0x08)")
    print()
    
    try:
        # Try using i2cdetect command
        result = subprocess.run(
            ['i2cdetect', '-y', '1'],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            print(result.stdout)
            
            # Parse output to find devices
            lines = result.stdout.strip().split('\n')[1:]  # Skip header
            devices = []
            for line in lines:
                parts = line.split(':')
                if len(parts) == 2:
                    for addr in parts[1].split():
                        if addr != '--' and addr != 'UU':
                            devices.append(f"0x{addr}")
            
            if devices:
                print(f"Found {len(devices)} device(s): {', '.join(devices)}")
                
                # Check for known devices
                if '0x04' in devices or '0x08' in devices:
                    print("✅ Grove Base HAT detected!")
            else:
                print("⚠️  No I2C devices found!")
                print("\nTroubleshooting:")
                print("  1. Make sure I2C is enabled: sudo raspi-config")
                print("  2. Check that Grove Base HAT is properly seated")
                print("  3. Reboot and try again")
        else:
            print(f"Error: {result.stderr}")
            
    except FileNotFoundError:
        print("Error: i2cdetect not found!")
        print("Install with: sudo apt-get install i2c-tools")
    except Exception as e:
        print(f"Error scanning I2C: {e}")

def show_pinout():
    """Display GPIO pinout information."""
    print_header("Raspberry Pi GPIO Pinout")
    
    # Try to use the pinout command from gpiozero
    try:
        result = subprocess.run(['pinout'], capture_output=True, text=True)
        if result.returncode == 0:
            print(result.stdout)
        else:
            show_manual_pinout()
    except FileNotFoundError:
        show_manual_pinout()

def show_manual_pinout():
    """Show manual pinout diagram."""
    print("""
    Raspberry Pi GPIO Header (40-pin)
    ==================================
    
    Grove Base HAT uses these connections:
    
    +-----+-----+---------+------+---+---Pi 2/3/4/Zero2W---+---+------+---------+-----+-----+
    | BCM | wPi |   Name  | Mode | V | Physical | V | Mode | Name    | wPi | BCM |
    +-----+-----+---------+------+---+----++----+---+------+---------+-----+-----+
    |     |     |    3.3v |      |   |  1 || 2  |   |      | 5v      |     |     |
    |   2 |   8 |   SDA.1 | ALT0 | 1 |  3 || 4  |   |      | 5v      |     |     |
    |   3 |   9 |   SCL.1 | ALT0 | 1 |  5 || 6  |   |      | GND     |     |     |
    |   4 |   7 | GPIO. 7 |   IN | 1 |  7 || 8  | 1 | ALT5 | TxD     | 15  | 14  |
    |     |     |     GND |      |   |  9 || 10 | 1 | ALT5 | RxD     | 16  | 15  |
    |  17 |   0 | GPIO. 0 |   IN | 0 | 11 || 12 | 0 | IN   | GPIO. 1 | 1   | 18  |
    |  27 |   2 | GPIO. 2 |   IN | 0 | 13 || 14 |   |      | GND     |     |     |
    |  22 |   3 | GPIO. 3 |   IN | 0 | 15 || 16 | 0 | IN   | GPIO. 4 | 4   | 23  |
    |     |     |    3.3v |      |   | 17 || 18 | 0 | IN   | GPIO. 5 | 5   | 24  |
    |  10 |  12 |    MOSI | ALT0 | 0 | 19 || 20 |   |      | GND     |     |     |
    |   9 |  13 |    MISO | ALT0 | 0 | 21 || 22 | 0 | IN   | GPIO. 6 | 6   | 25  |
    |  11 |  14 |    SCLK | ALT0 | 0 | 23 || 24 | 1 | OUT  | CE0     | 10  | 8   |
    |     |     |     GND |      |   | 25 || 26 | 1 | OUT  | CE1     | 11  | 7   |
    |   0 |  30 |   SDA.0 |   IN | 1 | 27 || 28 | 1 | IN   | SCL.0   | 31  | 1   |
    |   5 |  21 | GPIO.21 |   IN | 1 | 29 || 30 |   |      | GND     |     |     |
    |   6 |  22 | GPIO.22 |   IN | 1 | 31 || 32 | 0 | IN   | GPIO.26 | 26  | 12  |
    |  13 |  23 | GPIO.23 |   IN | 0 | 33 || 34 |   |      | GND     |     |     |
    |  19 |  24 | GPIO.24 |   IN | 0 | 35 || 36 | 0 | IN   | GPIO.27 | 27  | 16  |
    |  26 |  25 | GPIO.25 |   IN | 0 | 37 || 38 | 0 | IN   | GPIO.28 | 28  | 20  |
    |     |     |     GND |      |   | 39 || 40 | 0 | IN   | GPIO.29 | 29  | 21  |
    +-----+-----+---------+------+---+----++----+---+------+---------+-----+-----+
    
    Grove Base HAT Key Pins:
    - I2C: SDA (Pin 3, GPIO 2) and SCL (Pin 5, GPIO 3)
    - ADC: Uses I2C to communicate with onboard ADC chip
    
    Grove Analog Ports:
    - A0: ADC Channel 0
    - A2: ADC Channel 2
    - A4: ADC Channel 4
    - A6: ADC Channel 6
    """)

def read_all_adc():
    """Read all ADC channels from Grove Base HAT."""
    print_header("Grove Base HAT ADC Channels")
    
    try:
        from grove.adc import ADC
        adc = ADC()
        
        print("\nReading all 8 ADC channels...")
        print("(Grove ports are A0, A2, A4, A6)")
        print()
        print("Channel | Raw Value | Voltage (approx)")
        print("-" * 45)
        
        for channel in range(8):
            try:
                value = adc.read(channel)
                # Grove Base HAT ADC is 12-bit (0-4095) with 3.3V reference
                voltage = (value / 4095) * 3.3
                
                # Mark standard Grove ports
                port_label = ""
                if channel in [0, 2, 4, 6]:
                    port_label = f" <- Port A{channel}"
                
                print(f"   {channel}    |   {value:4d}    |   {voltage:.2f}V{port_label}")
            except Exception as e:
                print(f"   {channel}    |   Error   |   {e}")
        
        print()
        print("Note: Unconnected channels may show floating values")
        
    except ImportError:
        print("Error: grove.py library not found!")
        print("Please run the setup script first: sudo ./raspi-gpio-setup.sh")
    except Exception as e:
        print(f"Error reading ADC: {e}")
        print("\nTroubleshooting:")
        print("  1. Make sure Grove Base HAT is connected")
        print("  2. Verify I2C is enabled: sudo raspi-config")
        print("  3. Check I2C connection: i2cdetect -y 1")

def test_gpio_interactive():
    """Interactive GPIO pin testing."""
    print_header("Interactive GPIO Test")

    try:
        from gpiozero import DigitalInputDevice, DigitalOutputDevice
    except ImportError:
        print("Error: gpiozero library not found!")
        print("Please run the setup script first: sudo ./raspi-gpio-setup.sh")
        return
    except Exception as e:
        print(f"Error: {e}")
        print("This script must be run on a Raspberry Pi")
        return

    print("""
This will test basic GPIO functionality.

⚠️  WARNING: Be careful when testing GPIO pins!
   - Don't connect pins directly to 5V
   - Use current-limiting resistors with LEDs
   - Don't short pins together

Available tests:
  1. Read a GPIO pin (input mode)
  2. Toggle a GPIO pin (output mode)
  3. Exit
    """)

    active_device = None

    try:
        while True:
            choice = input("\nSelect test (1-3): ").strip()

            if choice == '1':
                try:
                    # Clean up previous device if any
                    if active_device:
                        active_device.close()
                        active_device = None

                    pin = int(input("Enter GPIO pin number (BCM): "))
                    device = DigitalInputDevice(pin, pull_up=True)
                    active_device = device

                    print(f"\nReading GPIO {pin} (press Ctrl+C to stop)...")
                    print("Pull the pin LOW (to GND) to see change")

                    last_state = None
                    try:
                        while True:
                            state = device.value
                            if state != last_state:
                                print(f"  GPIO {pin} = {'HIGH (1)' if state else 'LOW (0)'}")
                                last_state = state
                            time.sleep(0.1)
                    except KeyboardInterrupt:
                        print("\nStopped reading.")

                except ValueError:
                    print("Invalid pin number!")
                except Exception as e:
                    print(f"Error: {e}")

            elif choice == '2':
                try:
                    # Clean up previous device if any
                    if active_device:
                        active_device.close()
                        active_device = None

                    pin = int(input("Enter GPIO pin number (BCM): "))
                    device = DigitalOutputDevice(pin)
                    active_device = device

                    print(f"\nToggling GPIO {pin} (press Ctrl+C to stop)...")

                    try:
                        state = False
                        while True:
                            if state:
                                device.on()
                            else:
                                device.off()
                            print(f"  GPIO {pin} = {'HIGH' if state else 'LOW'}")
                            state = not state
                            time.sleep(1)
                    except KeyboardInterrupt:
                        device.off()
                        print("\nStopped toggling. Pin set to LOW.")

                except ValueError:
                    print("Invalid pin number!")
                except Exception as e:
                    print(f"Error: {e}")

            elif choice == '3':
                break
            else:
                print("Invalid choice!")

    finally:
        if active_device:
            active_device.close()
        print("\nGPIO cleanup complete.")

def check_libraries():
    """Check installed GPIO libraries."""
    print_header("Installed Libraries Check")
    
    libraries = [
        ('gpiozero', 'gpiozero'),
        ('lgpio', 'lgpio'),
        ('smbus2', 'smbus2'),
        ('grove.py', 'grove'),
    ]
    
    print("\nChecking Python GPIO libraries...")
    print()
    
    for name, module in libraries:
        try:
            __import__(module)
            version = ""
            try:
                import importlib
                mod = importlib.import_module(module)
                if hasattr(mod, '__version__'):
                    version = f" (v{mod.__version__})"
                elif hasattr(mod, 'VERSION'):
                    version = f" (v{mod.VERSION})"
            except:
                pass
            print(f"  ✅ {name}{version}")
        except ImportError:
            print(f"  ❌ {name} - NOT INSTALLED")
    
    print()
    
    # Check system tools
    print("Checking system tools...")
    print()

    tools = ['i2cdetect', 'gpiodetect', 'pinout']
    for tool in tools:
        result = subprocess.run(['which', tool], capture_output=True)
        if result.returncode == 0:
            print(f"  ✅ {tool}")
        else:
            print(f"  ❌ {tool} - NOT FOUND")

def run_all_tests():
    """Run all diagnostic tests."""
    check_libraries()
    scan_i2c()
    show_pinout()
    read_all_adc()
    print_header("Tests Complete")
    print("\nAll diagnostic tests have been run.")
    print("Review the output above for any issues.")

def main():
    print("""
╔══════════════════════════════════════════════════════════╗
║     Raspberry Pi GPIO Testing Utility                    ║
║     For Grove Base HAT + Moisture Sensors                ║
╚══════════════════════════════════════════════════════════╝
    """)
    
    # Get command from argument or show menu
    if len(sys.argv) > 1:
        command = sys.argv[1].lower()
    else:
        print("Commands:")
        print("  scan   - Scan I2C bus for devices")
        print("  pinout - Show GPIO pinout information")
        print("  adc    - Read all ADC channels")
        print("  gpio   - Interactive GPIO pin test")
        print("  libs   - Check installed libraries")
        print("  all    - Run all tests")
        print()
        command = input("Enter command (or press Enter for 'scan'): ").strip().lower()
        if not command:
            command = 'scan'
    
    # Execute command
    commands = {
        'scan': scan_i2c,
        'i2c': scan_i2c,
        'pinout': show_pinout,
        'pins': show_pinout,
        'adc': read_all_adc,
        'analog': read_all_adc,
        'gpio': test_gpio_interactive,
        'test': test_gpio_interactive,
        'libs': check_libraries,
        'libraries': check_libraries,
        'all': run_all_tests,
    }
    
    if command in commands:
        commands[command]()
    else:
        print(f"Unknown command: {command}")
        print("Valid commands: scan, pinout, adc, gpio, libs, all")
        sys.exit(1)

if __name__ == "__main__":
    main()
