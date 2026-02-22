import logging
import os
from typing import List, Dict, Any, Optional
from influxdb_client import InfluxDBClient
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class InfluxQueryClient:
    def __init__(self):
        """Initialize InfluxDB query client"""
        self.url = os.getenv("INFLUXDB_URL", "http://localhost:8086")
        self.token = os.getenv("INFLUXDB_TOKEN", "")
        self.org = os.getenv("INFLUXDB_ORG", "moisture-monitoring")
        self.bucket = os.getenv("INFLUXDB_BUCKET", "sensor-data")

        self.client = InfluxDBClient(
            url=self.url,
            token=self.token,
            org=self.org
        )

        self.query_api = self.client.query_api()

        logger.info(f"InfluxDB query client initialized: {self.url}")

    def get_current_readings(self) -> List[Dict[str, Any]]:
        """Get the most recent reading for each sensor"""
        # Cast _value to float before pivot to avoid "schema collision: cannot group float and integer"
        query = f'''
        from(bucket: "{self.bucket}")
            |> range(start: -1h)
            |> filter(fn: (r) => r["_measurement"] == "moisture_reading")
            |> group(columns: ["agent_id", "sensor_channel"])
            |> last()
            |> map(fn: (r) => ({{ r with _value: float(v: r._value) }}))
            |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
        '''

        try:
            result = self.query_api.query(query)

            readings = []
            for table in result:
                for record in table.records:
                    readings.append({
                        "agent_id": record.values.get("agent_id"),
                        "sensor_channel": int(record.values.get("sensor_channel", 0)),
                        "sensor_type": record.values.get("sensor_type"),
                        "location": record.values.get("location"),
                        "plant_type": record.values.get("plant_type"),
                        "sensor_name": record.values.get("sensor_name"),
                        "timestamp": record.values.get("_time").isoformat(),
                        "raw_value": int(record.values.get("raw_value", 0)),
                        "moisture_percent": float(record.values.get("moisture_percent", 0.0))
                    })

            return readings

        except Exception as e:
            logger.error(f"Failed to query current readings: {e}")
            return []

    def get_sensor_timeseries(
        self,
        agent_id: str,
        sensor_channel: int,
        hours: int = 24
    ) -> List[Dict[str, Any]]:
        """Get time-series data for a specific sensor"""
        query = f'''
        from(bucket: "{self.bucket}")
            |> range(start: -{hours}h)
            |> filter(fn: (r) => r["_measurement"] == "moisture_reading")
            |> filter(fn: (r) => r["agent_id"] == "{agent_id}")
            |> filter(fn: (r) => r["sensor_channel"] == "{sensor_channel}")
            |> filter(fn: (r) => r["_field"] == "moisture_percent")
            |> aggregateWindow(every: 5m, fn: mean, createEmpty: false)
        '''

        try:
            result = self.query_api.query(query)

            data_points = []
            for table in result:
                for record in table.records:
                    data_points.append({
                        "timestamp": record.values.get("_time").isoformat(),
                        "moisture_percent": float(record.values.get("_value", 0.0))
                    })

            return data_points

        except Exception as e:
            logger.error(f"Failed to query sensor timeseries: {e}")
            return []

    def get_sensor_summary(
        self,
        agent_id: str,
        sensor_channel: int,
        hours: int = 24
    ) -> Dict[str, float]:
        """Get summary statistics for a sensor"""
        query = f'''
        data = from(bucket: "{self.bucket}")
            |> range(start: -{hours}h)
            |> filter(fn: (r) => r["_measurement"] == "moisture_reading")
            |> filter(fn: (r) => r["agent_id"] == "{agent_id}")
            |> filter(fn: (r) => r["sensor_channel"] == "{sensor_channel}")
            |> filter(fn: (r) => r["_field"] == "moisture_percent")

        min = data |> min()
        max = data |> max()
        mean = data |> mean()

        union(tables: [min, max, mean])
        '''

        try:
            result = self.query_api.query(query)

            summary = {}
            for table in result:
                for record in table.records:
                    field = record.values.get("_field")
                    value = float(record.values.get("_value", 0.0))

                    # Extract stat type from table name
                    if "min" in str(table):
                        summary["min"] = value
                    elif "max" in str(table):
                        summary["max"] = value
                    elif "mean" in str(table):
                        summary["avg"] = value

            return summary

        except Exception as e:
            logger.error(f"Failed to query sensor summary: {e}")
            return {}

    def close(self):
        """Close InfluxDB client"""
        if self.client:
            self.client.close()
