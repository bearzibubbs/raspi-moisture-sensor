#!/bin/bash
#
# Raspberry Pi GPIO Setup Script for Grove Moisture Sensors
# Tested on: Raspberry Pi Zero 2 W with Grove Base HAT
#
# This script installs all necessary software for testing GPIO pins
# and working with Grove moisture sensors (resistive and capacitive)
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN} Raspberry Pi GPIO Setup Script${NC}"
echo -e "${GREEN} Grove Base HAT + Moisture Sensors${NC}"
echo -e "${GREEN}========================================${NC}"
echo

# Check if running on Raspberry Pi
if [ ! -f /proc/device-tree/model ]; then
    echo -e "${YELLOW}Warning: This doesn't appear to be a Raspberry Pi.${NC}"
    echo -e "${YELLOW}Script may not work correctly on this system.${NC}"
    read -p "Continue anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
else
    MODEL=$(cat /proc/device-tree/model)
    echo -e "Detected: ${GREEN}$MODEL${NC}"
    echo
fi

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}Please run as root (use sudo)${NC}"
    exit 1
fi

echo -e "${YELLOW}Step 1/5: Updating system packages...${NC}"
apt-get update -y
apt-get upgrade -y

echo
echo -e "${YELLOW}Step 2/5: Installing system dependencies...${NC}"
apt-get install -y \
    python3-dev \
    python3-pip \
    python3-venv \
    i2c-tools \
    gpiod \
    libgpiod-dev \
    git

echo
echo -e "${YELLOW}Step 3/5: Enabling I2C interface...${NC}"
# Enable I2C via raspi-config non-interactively
if command -v raspi-config &> /dev/null; then
    raspi-config nonint do_i2c 0
    echo -e "${GREEN}I2C enabled successfully${NC}"
else
    echo -e "${YELLOW}raspi-config not found. Please enable I2C manually.${NC}"
fi

# Add user to gpio and i2c groups
SUDO_USER_NAME=${SUDO_USER:-$USER}
if [ "$SUDO_USER_NAME" != "root" ]; then
    usermod -aG gpio,i2c "$SUDO_USER_NAME" 2>/dev/null || true
    echo -e "${GREEN}Added $SUDO_USER_NAME to gpio and i2c groups${NC}"
fi

echo
echo -e "${YELLOW}Step 4/5: Installing Python GPIO libraries...${NC}"
# Install Python libraries system-wide
# gpiozero with lgpio backend is the recommended approach for modern Raspberry Pi OS
pip3 install --break-system-packages \
    gpiozero \
    lgpio \
    smbus2 2>/dev/null || \
pip3 install \
    gpiozero \
    lgpio \
    smbus2

echo
echo -e "${YELLOW}Step 5/5: Installing Seeed Grove.py library...${NC}"
# Install grove.py from Seeed Studio
pip3 install --break-system-packages grove.py 2>/dev/null || \
pip3 install grove.py 2>/dev/null || {
    echo -e "${YELLOW}Installing grove.py from source...${NC}"
    cd /tmp
    git clone https://github.com/Seeed-Studio/grove.py.git
    cd grove.py
    pip3 install --break-system-packages . 2>/dev/null || pip3 install .
    cd -
    rm -rf /tmp/grove.py
}

echo
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN} Installation Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo
echo -e "${YELLOW}Post-Installation Notes:${NC}"
echo
echo "1. A REBOOT is recommended to ensure I2C is fully enabled"
echo "   Run: sudo reboot"
echo
echo "2. After reboot, verify I2C is working:"
echo "   Run: i2cdetect -y 1"
echo "   You should see the Grove Base HAT at address 0x04 or 0x08"
echo
echo "3. Check GPIO pinout at any time:"
echo "   Run: pinout"
echo
echo "4. Test your sensors with the included scripts:"
echo "   - test_grove_moisture.py (resistive sensor)"
echo "   - test_grove_capacitive.py (capacitive sensor)"
echo "   - gpio_pin_test.py (general GPIO testing)"
echo
echo -e "${YELLOW}Grove Base HAT ADC Channels:${NC}"
echo "   A0 = Analog port 0 (pin A0)"
echo "   A2 = Analog port 1 (pin A2)"
echo "   A4 = Analog port 2 (pin A4)"
echo "   A6 = Analog port 3 (pin A6)"
echo
echo -e "${GREEN}Happy sensing! 🌱${NC}"
