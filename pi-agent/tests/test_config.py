import pytest
from pathlib import Path
from config import AgentConfig, SensorConfig


def test_load_config_from_yaml(tmp_path):
    """Test loading configuration from YAML file"""
    config_file = tmp_path / "test_config.yaml"
    config_file.write_text("""
agent:
  id: "pi-test-01"
  orchestrator_url: "https://orch.example.com"
  sync_interval_seconds: 60

sensors:
  - channel: 0
    type: "capacitive"
    calibration:
      min: 300
      max: 800
    labels:
      location: "greenhouse"
      plant_type: "tomato"
      sensor_name: "tomato-01"
    thresholds:
      dry_percent: 30
      wet_percent: 85
      hysteresis: 5
""")

    config = AgentConfig.from_yaml(config_file)

    assert config.agent.id == "pi-test-01"
    assert config.agent.orchestrator_url == "https://orch.example.com"
    assert len(config.sensors) == 1
    assert config.sensors[0].channel == 0
    assert config.sensors[0].type == "capacitive"
    assert config.sensors[0].labels.location == "greenhouse"


def test_config_validation_invalid_channel():
    """Test config validation rejects invalid sensor channels"""
    with pytest.raises(ValueError):
        SensorConfig(
            channel=99,  # Invalid - must be 0-7
            type="capacitive",
            calibration={"min": 300, "max": 800},
            labels={"location": "test"},
            thresholds={"dry_percent": 30, "wet_percent": 85}
        )


def test_config_env_var_substitution(tmp_path, monkeypatch):
    """Test environment variable substitution in config"""
    monkeypatch.setenv("AGENT_ID", "pi-from-env")

    config_file = tmp_path / "test_config.yaml"
    config_file.write_text("""
agent:
  id: "${AGENT_ID}"
  orchestrator_url: "https://orch.example.com"
  sync_interval_seconds: 60

sensors: []
""")

    config = AgentConfig.from_yaml(config_file)
    assert config.agent.id == "pi-from-env"
