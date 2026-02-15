# Pi Agent - Moisture Sensor Data Collector

Autonomous agent for Raspberry Pi that reads moisture sensors and syncs to orchestrator.

## Installation

See parent repo's install-agent.sh script.

## Development

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-dev.txt
pytest
```

## Configuration

Edit config.yaml or set environment variables. See config.example.yaml.
