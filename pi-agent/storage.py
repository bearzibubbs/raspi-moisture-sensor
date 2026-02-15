import sqlite3
import time
from pathlib import Path
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, asdict


@dataclass
class Reading:
    timestamp: int
    sensor_channel: int
    sensor_type: str
    raw_value: int
    moisture_percent: float
    location: str
    plant_type: str
    sensor_name: str
    synced: bool = False
    id: Optional[int] = None


class StorageManager:
    def __init__(self, database_path: str):
        self.database_path = database_path
        self.conn: Optional[sqlite3.Connection] = None

    def initialize(self):
        """Initialize database and create tables if they don't exist"""
        # Create parent directory if needed
        Path(self.database_path).parent.mkdir(parents=True, exist_ok=True)

        self.conn = sqlite3.connect(self.database_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row

        # Create tables
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS readings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp INTEGER NOT NULL,
                sensor_channel INTEGER NOT NULL,
                sensor_type TEXT NOT NULL,
                raw_value INTEGER NOT NULL,
                moisture_percent REAL NOT NULL,
                location TEXT,
                plant_type TEXT,
                sensor_name TEXT,
                synced BOOLEAN DEFAULT 0,
                created_at INTEGER DEFAULT (strftime('%s','now'))
            )
        """)

        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_timestamp ON readings(timestamp)
        """)

        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_synced ON readings(synced)
        """)

        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_sensor ON readings(sensor_channel)
        """)

        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS agent_metadata (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)

        self.conn.commit()

    def store_reading(self, reading: Reading) -> int:
        """Store a sensor reading, returns the reading ID"""
        cursor = self.conn.execute("""
            INSERT INTO readings (
                timestamp, sensor_channel, sensor_type, raw_value,
                moisture_percent, location, plant_type, sensor_name, synced
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            reading.timestamp,
            reading.sensor_channel,
            reading.sensor_type,
            reading.raw_value,
            reading.moisture_percent,
            reading.location,
            reading.plant_type,
            reading.sensor_name,
            reading.synced
        ))
        self.conn.commit()
        return cursor.lastrowid

    def get_unsynced_readings(self, limit: int = 1000) -> List[Dict[str, Any]]:
        """Get unsynced readings, oldest first"""
        cursor = self.conn.execute("""
            SELECT * FROM readings
            WHERE synced = 0
            ORDER BY timestamp ASC
            LIMIT ?
        """, (limit,))

        rows = cursor.fetchall()
        return [dict(row) for row in rows]

    def mark_synced(self, reading_ids: List[int]):
        """Mark readings as synced"""
        if not reading_ids:
            return

        placeholders = ','.join('?' * len(reading_ids))
        self.conn.execute(f"""
            UPDATE readings
            SET synced = 1
            WHERE id IN ({placeholders})
        """, reading_ids)
        self.conn.commit()

    def cleanup_old_synced(self, days: int = 30) -> int:
        """Delete synced readings older than specified days, returns count deleted"""
        cutoff_timestamp = int(time.time()) - (days * 24 * 3600)

        cursor = self.conn.execute("""
            DELETE FROM readings
            WHERE synced = 1 AND timestamp < ?
        """, (cutoff_timestamp,))

        self.conn.commit()
        return cursor.rowcount

    def get_metadata(self, key: str) -> Optional[str]:
        """Get metadata value by key"""
        cursor = self.conn.execute("""
            SELECT value FROM agent_metadata WHERE key = ?
        """, (key,))

        row = cursor.fetchone()
        return row[0] if row else None

    def set_metadata(self, key: str, value: str):
        """Set metadata key-value pair"""
        self.conn.execute("""
            INSERT OR REPLACE INTO agent_metadata (key, value)
            VALUES (?, ?)
        """, (key, value))
        self.conn.commit()

    def get_database_size_mb(self) -> float:
        """Get database file size in MB"""
        if Path(self.database_path).exists():
            size_bytes = Path(self.database_path).stat().st_size
            return size_bytes / (1024 * 1024)
        return 0.0

    def vacuum(self):
        """Run VACUUM to reclaim space"""
        self.conn.execute("VACUUM")

    def close(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()
