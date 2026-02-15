import os
import re
from pathlib import Path
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator
import yaml


class SensorLabels(BaseModel):
    location: str = Field(..., min_length=1)
    plant_type: str = Field(..., min_length=1)
    sensor_name: str = Field(..., min_length=1)


class SensorThresholds(BaseModel):
    dry_percent: float = Field(..., ge=0, le=100)
    wet_percent: float = Field(..., ge=0, le=100)
    hysteresis: float = Field(default=5, ge=0, le=20)


class SensorCalibration(BaseModel):
    min: int = Field(..., ge=0, le=1023)
    max: int = Field(..., ge=0, le=1023)


class SensorConfig(BaseModel):
    channel: int = Field(..., ge=0, le=7)
    type: str = Field(..., pattern="^(capacitive|resistive)$")
    calibration: SensorCalibration
    labels: SensorLabels
    thresholds: SensorThresholds

    @field_validator('channel')
    @classmethod
    def validate_channel(cls, v):
        # Grove HAT only supports channels 0, 2, 4, 6 for analog ports
        if v not in [0, 2, 4, 6]:
            raise ValueError(f"Channel must be 0, 2, 4, or 6 (Grove analog ports), got {v}")
        return v


class AgentSettings(BaseModel):
    id: str = Field(..., min_length=1)
    orchestrator_url: str = Field(..., pattern="^https?://")
    bootstrap_token: Optional[str] = None
    agent_token: Optional[str] = None
    sync_interval_seconds: int = Field(default=60, ge=10, le=3600)
    config_pull_interval_seconds: int = Field(default=300, ge=60, le=3600)


class LocalAPISettings(BaseModel):
    enabled: bool = True
    port: int = Field(default=8080, ge=1024, le=65535)
    bearer_token: Optional[str] = None


class StorageSettings(BaseModel):
    database_path: str = "/var/lib/pi-agent/readings.db"
    cleanup_synced_older_than_days: int = Field(default=30, ge=1)
    max_db_size_mb: int = Field(default=500, ge=10)


class AgentConfig(BaseModel):
    agent: AgentSettings
    sensors: List[SensorConfig]
    local_api: LocalAPISettings = LocalAPISettings()
    storage: StorageSettings = StorageSettings()

    @classmethod
    def from_yaml(cls, path: Path) -> "AgentConfig":
        """Load config from YAML file with environment variable substitution"""
        with open(path) as f:
            content = f.read()

        # Substitute environment variables ${VAR_NAME}
        def replace_env_var(match):
            var_name = match.group(1)
            return os.getenv(var_name, match.group(0))

        content = re.sub(r'\$\{([A-Z_]+)\}', replace_env_var, content)

        data = yaml.safe_load(content)
        return cls(**data)
