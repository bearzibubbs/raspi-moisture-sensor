import logging
from typing import Dict, Any, Optional
from fastapi import FastAPI, HTTPException, Depends, Header
from pydantic import BaseModel
import psutil
from pathlib import Path
from config import AgentConfig
from storage import StorageManager


logger = logging.getLogger(__name__)


# Request/Response models
class HealthResponse(BaseModel):
    status: str
    agent_id: str
    uptime_seconds: float
    sensors: Dict[str, Dict[str, Any]]
    storage: Dict[str, Any]
    orchestrator: Dict[str, Any]
    system: Dict[str, float]


class StorageStatsResponse(BaseModel):
    db_size_mb: float
    unsynced_readings: int
    total_readings: int


class SensorTestResponse(BaseModel):
    channel: int
    success: bool
    raw_value: Optional[int]
    moisture_percent: Optional[float]
    error: Optional[str]


# Global state (will be initialized by main service)
app = FastAPI(title="Pi Agent API", version="1.0.0")
_config: Optional[AgentConfig] = None
_storage: Optional[StorageManager] = None
_agent_start_time: Optional[float] = None
_last_sync_time: Optional[str] = None
_orchestrator_connected: bool = False


def init_api(config: AgentConfig, storage: StorageManager, start_time: float):
    """Initialize API with config and storage"""
    global _config, _storage, _agent_start_time
    _config = config
    _storage = storage
    _agent_start_time = start_time


def set_config(config: AgentConfig):
    """Update in-memory config (e.g. after pulling from orchestrator)"""
    global _config
    _config = config


def verify_bearer_token(authorization: str = Header(None)):
    """Verify bearer token from local_api settings"""
    if not _config or not _config.local_api.bearer_token:
        # No auth configured
        return

    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header required")

    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization format")

    token = authorization.split(" ", 1)[1]

    if token != _config.local_api.bearer_token:
        raise HTTPException(status_code=401, detail="Invalid bearer token")


@app.get("/health", response_model=HealthResponse)
async def get_health(auth: None = Depends(verify_bearer_token)):
    """Get agent health status"""
    if not _config or not _storage:
        raise HTTPException(status_code=503, detail="Agent not initialized")

    import time
    uptime = time.time() - _agent_start_time if _agent_start_time else 0

    # Get sensor statuses (simplified - would check actual sensor reads in production)
    sensors_status = {}
    for sensor in _config.sensors:
        sensors_status[str(sensor.channel)] = {
            "status": "ok",
            "type": sensor.type,
            "location": sensor.labels.location,
            "plant_type": sensor.labels.plant_type
        }

    # Get storage stats
    unsynced = len(_storage.get_unsynced_readings(limit=1))

    # Get system metrics
    system_metrics = {
        "cpu_percent": psutil.cpu_percent(interval=0.1),
        "memory_percent": psutil.virtual_memory().percent,
        "disk_percent": psutil.disk_usage('/').percent,
        "cpu_temp_c": get_cpu_temperature()
    }

    return HealthResponse(
        status="healthy",
        agent_id=_config.agent.id,
        uptime_seconds=uptime,
        sensors=sensors_status,
        storage={
            "db_size_mb": round(_storage.get_database_size_mb(), 2),
            "unsynced_readings": unsynced
        },
        orchestrator={
            "connected": _orchestrator_connected,
            "last_sync": _last_sync_time or "never"
        },
        system=system_metrics
    )


@app.get("/config")
async def get_config(auth: None = Depends(verify_bearer_token)):
    """Get current configuration"""
    if not _config:
        raise HTTPException(status_code=503, detail="Agent not initialized")

    return _config.model_dump()


@app.get("/sensors")
async def list_sensors(auth: None = Depends(verify_bearer_token)):
    """List all configured sensors"""
    if not _config:
        raise HTTPException(status_code=503, detail="Agent not initialized")

    return {
        "sensors": [
            {
                "channel": s.channel,
                "type": s.type,
                "location": s.labels.location,
                "plant_type": s.labels.plant_type,
                "sensor_name": s.labels.sensor_name,
                "calibration": {
                    "min": s.calibration.min,
                    "max": s.calibration.max
                },
                "thresholds": {
                    "dry_percent": s.thresholds.dry_percent,
                    "wet_percent": s.thresholds.wet_percent
                }
            }
            for s in _config.sensors
        ]
    }


@app.get("/sensors/{channel}")
async def get_sensor(channel: int, auth: None = Depends(verify_bearer_token)):
    """Get specific sensor configuration"""
    if not _config:
        raise HTTPException(status_code=503, detail="Agent not initialized")

    for sensor in _config.sensors:
        if sensor.channel == channel:
            return sensor.model_dump()

    raise HTTPException(status_code=404, detail=f"Sensor channel {channel} not found")


@app.get("/readings/recent")
async def get_recent_readings(limit: int = 100, auth: None = Depends(verify_bearer_token)):
    """Get recent readings from storage"""
    if not _storage:
        raise HTTPException(status_code=503, detail="Agent not initialized")

    # Get recent readings (would need a new storage method for this)
    # For now, return unsynced as proxy
    readings = _storage.get_unsynced_readings(limit=limit)

    return {
        "count": len(readings),
        "readings": readings
    }


@app.get("/storage/stats", response_model=StorageStatsResponse)
async def get_storage_stats(auth: None = Depends(verify_bearer_token)):
    """Get storage statistics"""
    if not _storage:
        raise HTTPException(status_code=503, detail="Agent not initialized")

    unsynced_count = len(_storage.get_unsynced_readings(limit=10000))

    # Would need total count query - approximate for now
    return StorageStatsResponse(
        db_size_mb=round(_storage.get_database_size_mb(), 2),
        unsynced_readings=unsynced_count,
        total_readings=unsynced_count  # Approximation
    )


def get_cpu_temperature() -> float:
    """Get Raspberry Pi CPU temperature"""
    try:
        temp_file = Path("/sys/class/thermal/thermal_zone0/temp")
        if temp_file.exists():
            temp_millidegrees = int(temp_file.read_text().strip())
            return temp_millidegrees / 1000.0
    except Exception as e:
        logger.warning(f"Could not read CPU temperature: {e}")

    return 0.0
