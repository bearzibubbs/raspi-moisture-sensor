#!/usr/bin/env python3
"""
API Server - Homepage Integration

Queries InfluxDB and PostgreSQL to serve data to Homepage dashboard.
"""

import logging
import sys
import os
from typing import List, Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from influx_client import InfluxQueryClient

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="Moisture Monitoring API Server",
    version="1.0.0",
    description="API server for Homepage dashboard integration"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global clients
influx_client: InfluxQueryClient = None

# PostgreSQL connection for alerts
DATABASE_URL = os.getenv(
    "POSTGRES_URL",
    "postgresql://postgres:postgres@localhost:5432/moisture_monitoring"
)
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)


# Response models
class CurrentReading(BaseModel):
    agent_id: str
    sensor_channel: int
    sensor_type: str
    location: str
    plant_type: str
    sensor_name: str
    timestamp: str
    moisture_percent: float
    raw_value: int
    status: str


class CurrentReadingsResponse(BaseModel):
    sensors: List[CurrentReading]
    last_updated: str


class TimeSeriesPoint(BaseModel):
    timestamp: str
    moisture_percent: float


class SensorTimeSeriesResponse(BaseModel):
    agent_id: str
    channel: int
    location: str
    plant_type: str
    sensor_name: str
    data_points: List[TimeSeriesPoint]
    summary: dict


class Alert(BaseModel):
    id: int
    agent_id: str
    location: str
    plant_type: str
    sensor_name: str
    channel: int
    alert_type: str
    moisture_percent: Optional[float]
    threshold: Optional[float]
    triggered_at: str
    acknowledged: bool


class AlertsResponse(BaseModel):
    alerts: List[Alert]
    count: int


class FleetStatusResponse(BaseModel):
    total_agents: int
    online_agents: int
    offline_agents: int
    total_sensors: int
    active_alerts: int
    last_reading: Optional[str]


@app.on_event("startup")
async def startup_event():
    """Initialize services on startup"""
    global influx_client

    logger.info("Starting API server")
    influx_client = InfluxQueryClient()
    logger.info("API server started successfully")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    if influx_client:
        influx_client.close()
    logger.info("API server shut down")


def get_status_from_moisture(moisture_percent: float) -> str:
    """Determine status string from moisture percentage"""
    if moisture_percent < 20:
        return "very_dry"
    elif moisture_percent < 40:
        return "dry"
    elif moisture_percent < 60:
        return "moist"
    elif moisture_percent < 80:
        return "wet"
    else:
        return "very_wet"


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "Moisture Monitoring API Server",
        "version": "1.0.0",
        "status": "running"
    }


@app.get("/health")
async def health():
    """Health check endpoint"""
    return {"status": "healthy"}


@app.get("/api/v1/sensors/current", response_model=CurrentReadingsResponse)
async def get_current_readings():
    """Get current readings for all sensors (for Homepage widget)"""

    if not influx_client:
        raise HTTPException(status_code=503, detail="InfluxDB not available")

    readings = influx_client.get_current_readings()

    current_readings = [
        CurrentReading(
            agent_id=r["agent_id"],
            sensor_channel=r["sensor_channel"],
            sensor_type=r["sensor_type"],
            location=r["location"],
            plant_type=r["plant_type"],
            sensor_name=r["sensor_name"],
            timestamp=r["timestamp"],
            moisture_percent=r["moisture_percent"],
            raw_value=r["raw_value"],
            status=get_status_from_moisture(r["moisture_percent"])
        )
        for r in readings
    ]

    last_updated = readings[0]["timestamp"] if readings else None

    return CurrentReadingsResponse(
        sensors=current_readings,
        last_updated=last_updated
    )


@app.get("/api/v1/sensors/{agent_id}/{channel}/timeseries", response_model=SensorTimeSeriesResponse)
async def get_sensor_timeseries(
    agent_id: str,
    channel: int,
    hours: int = 24
):
    """Get time-series data for a specific sensor"""

    if not influx_client:
        raise HTTPException(status_code=503, detail="InfluxDB not available")

    # Get time-series data
    data_points = influx_client.get_sensor_timeseries(agent_id, channel, hours)

    if not data_points:
        raise HTTPException(status_code=404, detail="No data found for sensor")

    # Get summary statistics
    summary = influx_client.get_sensor_summary(agent_id, channel, hours)

    # Get current reading for metadata
    current = influx_client.get_current_readings()
    sensor_info = next((r for r in current if r["agent_id"] == agent_id and r["sensor_channel"] == channel), None)

    if not sensor_info:
        raise HTTPException(status_code=404, detail="Sensor not found")

    points = [TimeSeriesPoint(**p) for p in data_points]

    return SensorTimeSeriesResponse(
        agent_id=agent_id,
        channel=channel,
        location=sensor_info["location"],
        plant_type=sensor_info["plant_type"],
        sensor_name=sensor_info["sensor_name"],
        data_points=points,
        summary=summary
    )


@app.get("/api/v1/alerts/active", response_model=AlertsResponse)
async def get_active_alerts():
    """Get active alerts (for Homepage widget)"""

    try:
        db = SessionLocal()

        # Query active alerts from PostgreSQL
        from sqlalchemy import text
        query = text("""
            SELECT id, agent_id, sensor_channel, alert_type,
                   moisture_percent, threshold, triggered_at, acknowledged,
                   location, plant_type, sensor_name
            FROM active_alerts
            WHERE resolved_at IS NULL
            ORDER BY triggered_at DESC
        """)

        result = db.execute(query)
        rows = result.fetchall()

        alerts = [
            Alert(
                id=row[0],
                agent_id=row[1],
                channel=row[2],
                alert_type=row[3],
                moisture_percent=row[4],
                threshold=row[5],
                triggered_at=row[6].isoformat() if row[6] else None,
                acknowledged=row[7],
                location=row[8],
                plant_type=row[9],
                sensor_name=row[10]
            )
            for row in rows
        ]

        db.close()

        return AlertsResponse(
            alerts=alerts,
            count=len(alerts)
        )

    except Exception as e:
        logger.error(f"Failed to query alerts: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/fleet/status", response_model=FleetStatusResponse)
async def get_fleet_status():
    """Get fleet status summary (for Homepage widget)"""

    try:
        db = SessionLocal()

        # Query agent statistics
        from sqlalchemy import text

        total_agents = db.execute(text("SELECT COUNT(*) FROM agents")).scalar()

        # Agents with recent heartbeat (last 10 minutes)
        online_agents = db.execute(text("""
            SELECT COUNT(*) FROM agents
            WHERE last_heartbeat > NOW() - INTERVAL '10 minutes'
        """)).scalar()

        offline_agents = total_agents - online_agents

        # Count active alerts
        active_alerts = db.execute(text("""
            SELECT COUNT(*) FROM active_alerts WHERE resolved_at IS NULL
        """)).scalar()

        db.close()

        # Get sensor count and last reading from InfluxDB
        if influx_client:
            readings = influx_client.get_current_readings()
            total_sensors = len(readings)
            last_reading = readings[0]["timestamp"] if readings else None
        else:
            total_sensors = 0
            last_reading = None

        return FleetStatusResponse(
            total_agents=total_agents,
            online_agents=online_agents,
            offline_agents=offline_agents,
            total_sensors=total_sensors,
            active_alerts=active_alerts,
            last_reading=last_reading
        )

    except Exception as e:
        logger.error(f"Failed to query fleet status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8001,
        log_level="info",
        reload=False
    )
