import logging
from datetime import datetime, timezone
from typing import List
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from database import get_db
from models import Agent
from auth import verify_agent_token
from influx import InfluxWriter

logger = logging.getLogger(__name__)
router = APIRouter(tags=["ingestion"])

# Global InfluxDB writer (initialized by main app)
influx_writer: InfluxWriter = None


def init_influx(writer: InfluxWriter):
    """Initialize global InfluxDB writer"""
    global influx_writer
    influx_writer = writer


# Request/Response models
class Reading(BaseModel):
    timestamp: int
    sensor_channel: int
    sensor_type: str
    raw_value: int
    moisture_percent: float
    location: str
    plant_type: str
    sensor_name: str


class UploadReadingsRequest(BaseModel):
    readings: List[Reading]


class UploadReadingsResponse(BaseModel):
    accepted: int
    rejected: int
    message: str


class HealthMetrics(BaseModel):
    cpu_percent: float = None
    memory_percent: float = None
    disk_percent: float = None
    cpu_temp_c: float = None


class AgentHealthRequest(BaseModel):
    uptime_seconds: float
    storage_db_size_mb: float
    storage_unsynced_readings: int
    system: HealthMetrics


@router.post("/agents/{agent_id}/readings", response_model=UploadReadingsResponse)
async def upload_readings(
    agent_id: str,
    request: UploadReadingsRequest,
    agent: Agent = Depends(verify_agent_token),
    db: Session = Depends(get_db)
):
    """Receive sensor readings from agent and write to InfluxDB"""

    # Verify agent_id matches token
    if agent.agent_id != agent_id:
        raise HTTPException(status_code=403, detail="Agent ID mismatch")

    if not influx_writer:
        raise HTTPException(status_code=503, detail="InfluxDB not available")

    if not request.readings:
        return UploadReadingsResponse(
            accepted=0,
            rejected=0,
            message="No readings provided"
        )

    # Convert Pydantic models to dicts for InfluxDB writer
    readings_data = [r.model_dump() for r in request.readings]

    try:
        # Write to InfluxDB
        written = influx_writer.write_readings(agent_id, readings_data)

        # Update agent last_sync timestamp
        agent.last_sync_at = datetime.now(timezone.utc)
        db.commit()

        logger.info(f"Accepted {written} readings from {agent_id}")

        return UploadReadingsResponse(
            accepted=written,
            rejected=0,
            message=f"Successfully stored {written} readings"
        )

    except Exception as e:
        logger.error(f"Failed to process readings from {agent_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to store readings: {str(e)}"
        )


@router.post("/agents/{agent_id}/health")
async def report_health(
    agent_id: str,
    request: AgentHealthRequest,
    agent: Agent = Depends(verify_agent_token),
    db: Session = Depends(get_db)
):
    """Receive health metrics from agent"""

    # Verify agent_id matches token
    if agent.agent_id != agent_id:
        raise HTTPException(status_code=403, detail="Agent ID mismatch")

    # Store health metrics in agent metadata
    health_data = {
        "uptime_seconds": request.uptime_seconds,
        "storage_db_size_mb": request.storage_db_size_mb,
        "storage_unsynced_readings": request.storage_unsynced_readings,
        "system": request.system.model_dump(),
        "reported_at": datetime.now(timezone.utc).isoformat()
    }

    # Update or create metadata
    if agent.agent_metadata:
        agent.agent_metadata["health"] = health_data
    else:
        agent.agent_metadata = {"health": health_data}

    db.commit()

    logger.debug(f"Health metrics received from {agent_id}")

    return {"status": "ok"}
