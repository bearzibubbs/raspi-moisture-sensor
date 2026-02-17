#!/bin/bash
#
# Pi Agent Installation Script
# Installs moisture sensor agent on Raspberry Pi
#

set -e

echo "=========================================="
echo " Pi Agent Installation"
echo "=========================================="
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "Error: Please run as root (use sudo)"
    exit 1
fi

# Check if running on Raspberry Pi
if [ ! -f /proc/device-tree/model ]; then
    echo "Warning: Not detected as Raspberry Pi, continuing anyway..."
fi

# Check required environment variables
if [ -z "$ORCHESTRATOR_URL" ]; then
    echo "Error: ORCHESTRATOR_URL environment variable not set"
    echo "Example: export ORCHESTRATOR_URL=https://orchestrator.example.com"
    exit 1
fi

if [ -z "$BOOTSTRAP_TOKEN" ]; then
    echo "Error: BOOTSTRAP_TOKEN environment variable not set"
    echo "Get this from your orchestrator admin"
    exit 1
fi

echo "Configuration:"
echo "  Orchestrator URL: $ORCHESTRATOR_URL"
echo "  Bootstrap Token: ${BOOTSTRAP_TOKEN:0:10}..."
echo ""

# Install system dependencies
echo "[1/8] Installing system dependencies..."
apt-get update
apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    i2c-tools \
    gpiod \
    git \
    cargo

# Enable I2C
echo "[2/8] Enabling I2C..."
if ! grep -q "^dtparam=i2c_arm=on" /boot/config.txt; then
    echo "dtparam=i2c_arm=on" >> /boot/config.txt
fi

# Load I2C kernel module
modprobe i2c-dev || true

# Create application directories
echo "[3/8] Creating directories..."
mkdir -p /opt/pi-agent
mkdir -p /var/lib/pi-agent
mkdir -p /var/log/pi-agent

# Copy agent files
echo "[4/8] Installing agent files..."
if [ -d "pi-agent" ]; then
    cp -r pi-agent/* /opt/pi-agent/
else
    echo "Error: pi-agent directory not found"
    exit 1
fi

# Create virtual environment and install dependencies
echo "[5/8] Installing Python dependencies..."
cd /opt/pi-agent
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# Generate agent ID if not exists
if [ ! -f /opt/pi-agent/.agent_id ]; then
    echo "[6/8] Generating agent ID..."
    AGENT_ID="pi-$(cat /sys/class/net/eth0/address 2>/dev/null || cat /sys/class/net/wlan0/address | sha256sum | cut -c1-12)"
    echo "$AGENT_ID" > /opt/pi-agent/.agent_id
    echo "  Generated: $AGENT_ID"
else
    AGENT_ID=$(cat /opt/pi-agent/.agent_id)
    echo "[6/8] Using existing agent ID: $AGENT_ID"
fi

# Generate local API token
if [ -z "$LOCAL_API_TOKEN" ]; then
    LOCAL_API_TOKEN=$(openssl rand -hex 32)
fi

# Create environment file
echo "[7/8] Creating configuration..."
cat > /opt/pi-agent/.env <<EOF
AGENT_ID=$AGENT_ID
ORCHESTRATOR_URL=$ORCHESTRATOR_URL
BOOTSTRAP_TOKEN=$BOOTSTRAP_TOKEN
LOCAL_API_TOKEN=$LOCAL_API_TOKEN
EOF

chmod 600 /opt/pi-agent/.env

# Copy example config if config doesn't exist
if [ ! -f /opt/pi-agent/config.yaml ]; then
    if [ -f /opt/pi-agent/config.example.yaml ]; then
        cp /opt/pi-agent/config.example.yaml /opt/pi-agent/config.yaml
        echo "  Created config.yaml from example"
        echo "  IMPORTANT: Edit /opt/pi-agent/config.yaml and set sensor labels!"
    fi
fi

# Create systemd service
echo "[8/8] Creating systemd service..."
cat > /etc/systemd/system/pi-agent.service <<EOF
[Unit]
Description=Moisture Sensor Agent
Documentation=https://github.com/bearzibubbs/raspi-moisture-sensor
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/pi-agent
EnvironmentFile=/opt/pi-agent/.env
ExecStart=/opt/pi-agent/venv/bin/python /opt/pi-agent/agent.py /opt/pi-agent/config.yaml
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

# Security settings
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF

# Reload systemd
systemctl daemon-reload

# Enable service (but don't start yet)
systemctl enable pi-agent

echo ""
echo "=========================================="
echo " Installation Complete!"
echo "=========================================="
echo ""
echo "Agent ID: $AGENT_ID"
echo "Local API Token: $LOCAL_API_TOKEN"
echo ""
echo "NEXT STEPS:"
echo "1. Edit sensor configuration: nano /opt/pi-agent/config.yaml"
echo "2. Update sensor labels (location, plant_type, sensor_name)"
echo "3. Start the service: systemctl start pi-agent"
echo "4. Check status: systemctl status pi-agent"
echo "5. View logs: journalctl -u pi-agent -f"
echo ""
echo "I2C device should be at 0x04 or 0x08:"
echo "  i2cdetect -y 1"
echo ""
echo "Reboot recommended to ensure I2C is enabled."
echo ""
