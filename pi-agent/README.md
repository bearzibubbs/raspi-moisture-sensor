# Pi Agent - Moisture Sensor Client

The Pi Agent runs on Raspberry Pi devices with Grove Base HAT and moisture sensors, collecting and syncing data to the orchestrator.

## Features

- **Autonomous operation** with local SQLite caching
- **Offline resilience** - queues readings when orchestrator is unreachable
- **Hardware support** for Grove Base HAT analog channels (0, 2, 4, 6)
- **Dual sensor types** - capacitive (inverted) and resistive (normal)
- **Pull-based configuration** - no SSH access needed for updates
- **Management API** - health checks and system metrics

## Deployment Options

### Option 1: Docker Container (Recommended)

**Prerequisites:**
- Docker or Podman installed
- I2C enabled on Raspberry Pi
- Grove Base HAT attached

**Quick Start:**

```bash
# Enable I2C (if not already enabled)
sudo raspi-config nonint do_i2c 0

# Add user to i2c group
sudo usermod -aG i2c $USER
# Log out and back in for group change to take effect

# Clone repository
git clone git@github.com:bearzibubbs/raspi-moisture-sensor.git
cd raspi-moisture-sensor/pi-agent

# Create configuration
cp config.example.yaml config.yaml
# Edit config.yaml with your sensor configuration

# Create environment file
cp .env.example .env
# Edit .env with your orchestrator URL

# Create data directory
mkdir -p data

# Start the agent
docker-compose up -d

# View logs
docker-compose logs -f

# Check status
docker-compose ps
curl http://localhost:8080/health
```

**Building the Image:**

```bash
docker build -t moisture-monitoring/pi-agent:latest .
```

**Updating:**

```bash
# Pull latest code
git pull

# Rebuild and restart
docker-compose up -d --build

# View logs
docker-compose logs -f pi-agent
```

### Option 2: Systemd Service

**Installation:**

```bash
# Run the installation script
sudo ORCHESTRATOR_URL=https://orchestrator.example.com \
     BOOTSTRAP_TOKEN=your-bootstrap-token \
     ./install-agent.sh

# Check status
sudo systemctl status moisture-pi-agent

# View logs
sudo journalctl -u moisture-pi-agent -f
```

See `install-agent.sh` for details.

### Option 3: Manual Installation (Development)

```bash
# Install system dependencies
sudo apt-get update
sudo apt-get install -y python3-pip python3-venv i2c-tools

# Enable I2C
sudo raspi-config nonint do_i2c 0

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Create configuration
cp config.example.yaml config.yaml
# Edit config.yaml

# Run agent
python agent.py

# Run tests
pytest
```

## Configuration

See `config.example.yaml` for full configuration options.

### Environment Variables

- `ORCHESTRATOR_URL` - Orchestrator endpoint (required)
- `AGENT_TOKEN` - Authentication token (auto-obtained on first run)
- `CONFIG_FILE` - Path to config.yaml (default: ./config.yaml)
- `DB_PATH` - SQLite database path (default: ./agent.db or /data/agent.db in container)
- `LOG_LEVEL` - Logging level (DEBUG, INFO, WARNING, ERROR)

## Sensor Calibration

### Capacitive Sensors

1. **Measure in air:**
   ```bash
   docker-compose exec pi-agent python -c "from collector import read_sensor; print(read_sensor(0))"
   ```
   Use this as `calibration.max`

2. **Measure in water:**
   ```bash
   docker-compose exec pi-agent python -c "from collector import read_sensor; print(read_sensor(0))"
   ```
   Use this as `calibration.min`

3. **Update config.yaml** with calibration values

### Resistive Sensors

Same process, but values are inverted (lower = drier, higher = wetter).

## Troubleshooting

### Container Cannot Access I2C

**Solutions:**

1. Verify I2C is enabled:
   ```bash
   ls -l /dev/i2c-1
   sudo i2cdetect -y 1
   ```

2. Check permissions:
   ```bash
   sudo chmod 666 /dev/i2c-1
   ```

3. Add user to i2c group:
   ```bash
   sudo usermod -aG i2c $USER
   ```

4. Use privileged mode (uncomment in docker-compose.yaml):
   ```yaml
   privileged: true
   ```

### Agent Won't Register

1. Verify orchestrator URL is accessible
2. Check bootstrap token (for first registration)
3. Review logs: `docker-compose logs pi-agent`

### Readings Seem Incorrect

1. Recalibrate sensors (see Calibration section)
2. Verify sensor type is correct (capacitive vs resistive)
3. Check sensor wiring to correct Grove channel

## Management API

Available at `http://localhost:8080`:

- `GET /health` - Health check and component status
- `GET /metrics` - System metrics (CPU, memory, disk, temperature)
- `GET /status` - Agent status (uptime, readings count, sync status)

## Maintenance

### View Logs

```bash
# Docker
docker-compose logs -f pi-agent

# Systemd
sudo journalctl -u moisture-pi-agent -f
```

### Restart Agent

```bash
# Docker
docker-compose restart pi-agent

# Systemd
sudo systemctl restart moisture-pi-agent
```

### Database Maintenance

```bash
# Check database size
docker-compose exec pi-agent ls -lh /data/agent.db

# Agent automatically cleans up old synced readings every 24h
```

### Backup

```bash
# Backup data directory
tar -czf pi-agent-backup-$(date +%Y%m%d).tar.gz data/

# Backup configuration
cp config.yaml config.yaml.backup
```
