import logging
import os
from typing import List, Dict, Any
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS
from datetime import datetime

logger = logging.getLogger(__name__)


class InfluxWriter:
    def __init__(self):
        """Initialize InfluxDB client"""
        self.url = os.getenv("INFLUXDB_URL", "http://localhost:8086")
        self.token = os.getenv("INFLUXDB_TOKEN", "")
        self.org = os.getenv("INFLUXDB_ORG", "moisture-monitoring")
        self.bucket = os.getenv("INFLUXDB_BUCKET", "sensor-data")

        self.client = InfluxDBClient(
            url=self.url,
            token=self.token,
            org=self.org
        )

        self.write_api = self.client.write_api(write_options=SYNCHRONOUS)

        logger.info(f"InfluxDB client initialized: {self.url}")

    def write_readings(self, agent_id: str, readings: List[Dict[str, Any]]) -> int:
        """
        Write sensor readings to InfluxDB.

        Args:
            agent_id: Agent identifier
            readings: List of reading dicts

        Returns:
            Number of readings written
        """
        if not readings:
            return 0

        points = []

        for reading in readings:
            # Create InfluxDB point
            point = Point("moisture_reading") \
                .tag("agent_id", agent_id) \
                .tag("sensor_channel", str(reading.get("sensor_channel"))) \
                .tag("sensor_type", reading.get("sensor_type", "")) \
                .tag("location", reading.get("location", "")) \
                .tag("plant_type", reading.get("plant_type", "")) \
                .tag("sensor_name", reading.get("sensor_name", "")) \
                .field("raw_value", int(reading.get("raw_value", 0))) \
                .field("moisture_percent", float(reading.get("moisture_percent", 0.0)))

            # Use timestamp from reading if available
            if "timestamp" in reading:
                timestamp = reading["timestamp"]
                if isinstance(timestamp, int):
                    # Unix timestamp
                    point = point.time(timestamp, write_precision='s')
                elif isinstance(timestamp, str):
                    # ISO format
                    point = point.time(datetime.fromisoformat(timestamp))

            points.append(point)

        try:
            # Write points to InfluxDB
            self.write_api.write(bucket=self.bucket, record=points)
            logger.info(f"Wrote {len(points)} readings from {agent_id} to InfluxDB")
            return len(points)

        except Exception as e:
            logger.error(f"Failed to write to InfluxDB: {e}", exc_info=True)
            raise

    def close(self):
        """Close InfluxDB client"""
        if self.client:
            self.client.close()
