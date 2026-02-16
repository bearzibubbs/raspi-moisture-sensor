# Moisture Monitoring System Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build an agent-based moisture monitoring system with autonomous Pi agents, central orchestrator, and Homepage dashboard integration.

**Architecture:** Three-tier system with Pi agents (data collection + local caching), Kubernetes orchestrator (fleet management + InfluxDB writes), and API server (Homepage integration). Agents operate autonomously with eventual consistency, pull-based configuration, and bearer token authentication.

**Tech Stack:** Python 3.11+, FastAPI, SQLite (agent), PostgreSQL (orchestrator), InfluxDB (time-series), APScheduler, httpx, grove.py, Kubernetes, Helm

---

## Phase 1: Pi Agent - Core Infrastructure

### Task 1.1: Project Structure & Dependencies

**Files:**
- Create: `pi-agent/requirements.txt`
- Create: `pi-agent/README.md`
- Create: `pi-agent/.gitignore`

**Step 1: Create requirements file**

Create `pi-agent/requirements.txt`:
```txt
fastapi==0.109.0
uvicorn[standard]==0.27.0
pydantic==2.5.3
pydantic-settings==2.1.0
httpx==0.26.0
apscheduler==3.10.4
python-multipart==0.0.6
grove.py==0.6
```

**Step 2: Create gitignore**

Create `pi-agent/.gitignore`:
```
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
*.db
*.sqlite3
.env
*.log
venv/
.vscode/
.pytest_cache/
.coverage
htmlcov/
```

**Step 3: Create README**

Create `pi-agent/README.md`:
```markdown
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
```

**Step 4: Commit**

```bash
git add pi-agent/
git commit -m "feat(agent): initialize project structure"
```

---

### Task 1.2: Configuration Management

**Files:**
- Create: `pi-agent/config.py`
- Create: `pi-agent/config.example.yaml`
- Create: `pi-agent/tests/test_config.py`

**Step 1: Write failing test for config loading**

Create `pi-agent/tests/test_config.py`:
```python
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
```

**Step 2: Run test to verify it fails**

Run: `cd pi-agent && pytest tests/test_config.py -v`

Expected: FAIL with "ModuleNotFoundError: No module named 'config'"

**Step 3: Implement config module**

Create `pi-agent/config.py`:
```python
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
```

**Step 4: Run test to verify it passes**

Run: `cd pi-agent && pytest tests/test_config.py -v`

Expected: PASS (all 3 tests)

**Step 5: Create example config**

Create `pi-agent/config.example.yaml`:
```yaml
agent:
  id: "${AGENT_ID}"  # Generated during setup
  orchestrator_url: "${ORCHESTRATOR_URL}"
  bootstrap_token: "${BOOTSTRAP_TOKEN}"  # For first registration
  agent_token: "${AGENT_TOKEN}"  # Permanent token (auto-populated)
  sync_interval_seconds: 60
  config_pull_interval_seconds: 300

sensors:
  - channel: 0
    type: "capacitive"
    calibration:
      min: 300
      max: 800
    labels:
      location: "EDIT_ME"
      plant_type: "EDIT_ME"
      sensor_name: "EDIT_ME"
    thresholds:
      dry_percent: 30
      wet_percent: 85
      hysteresis: 5

  - channel: 2
    type: "resistive"
    calibration:
      min: 0
      max: 950
    labels:
      location: "EDIT_ME"
      plant_type: "EDIT_ME"
      sensor_name: "EDIT_ME"
    thresholds:
      dry_percent: 30
      wet_percent: 85
      hysteresis: 5

local_api:
  enabled: true
  port: 8080
  bearer_token: "${LOCAL_API_TOKEN}"

storage:
  database_path: "/var/lib/pi-agent/readings.db"
  cleanup_synced_older_than_days: 30
  max_db_size_mb: 500
```

**Step 6: Add dev dependencies**

Create `pi-agent/requirements-dev.txt`:
```txt
pytest==7.4.4
pytest-cov==4.1.0
pytest-asyncio==0.23.3
pytest-mock==3.12.0
pyyaml==6.0.1
```

**Step 7: Commit**

```bash
git add pi-agent/config.py pi-agent/tests/test_config.py pi-agent/config.example.yaml pi-agent/requirements-dev.txt
git commit -m "feat(agent): add configuration management with validation"
```

---

### Task 1.3: SQLite Storage Layer

**Files:**
- Create: `pi-agent/storage.py`
- Create: `pi-agent/tests/test_storage.py`

**Step 1: Write failing test for storage operations**

Create `pi-agent/tests/test_storage.py`:
```python
import pytest
import time
from pathlib import Path
from storage import StorageManager, Reading


@pytest.fixture
def storage(tmp_path):
    """Create in-memory storage for testing"""
    db_path = tmp_path / "test.db"
    return StorageManager(str(db_path))


def test_initialize_database(storage):
    """Test database initialization creates tables"""
    # Should not raise
    storage.initialize()

    # Verify tables exist
    result = storage.conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    table_names = [r[0] for r in result]

    assert "readings" in table_names
    assert "agent_metadata" in table_names


def test_store_reading(storage):
    """Test storing a sensor reading"""
    storage.initialize()

    reading = Reading(
        timestamp=int(time.time()),
        sensor_channel=0,
        sensor_type="capacitive",
        raw_value=475,
        moisture_percent=65.5,
        location="greenhouse",
        plant_type="tomato",
        sensor_name="tomato-01"
    )

    storage.store_reading(reading)

    # Verify stored
    result = storage.conn.execute(
        "SELECT * FROM readings WHERE sensor_channel=0"
    ).fetchone()

    assert result is not None
    assert result[2] == 0  # sensor_channel
    assert result[4] == 475  # raw_value


def test_get_unsynced_readings(storage):
    """Test retrieving unsynced readings"""
    storage.initialize()

    # Store 5 readings
    for i in range(5):
        reading = Reading(
            timestamp=int(time.time()) + i,
            sensor_channel=0,
            sensor_type="capacitive",
            raw_value=400 + i,
            moisture_percent=60.0 + i,
            location="test",
            plant_type="test",
            sensor_name="test"
        )
        storage.store_reading(reading)

    unsynced = storage.get_unsynced_readings(limit=10)
    assert len(unsynced) == 5

    # Test limit
    unsynced_limited = storage.get_unsynced_readings(limit=3)
    assert len(unsynced_limited) == 3


def test_mark_readings_synced(storage):
    """Test marking readings as synced"""
    storage.initialize()

    reading = Reading(
        timestamp=int(time.time()),
        sensor_channel=0,
        sensor_type="capacitive",
        raw_value=475,
        moisture_percent=65.5,
        location="test",
        plant_type="test",
        sensor_name="test"
    )

    reading_id = storage.store_reading(reading)

    # Mark as synced
    storage.mark_synced([reading_id])

    # Verify no unsynced readings
    unsynced = storage.get_unsynced_readings()
    assert len(unsynced) == 0


def test_cleanup_old_synced_readings(storage):
    """Test cleanup of old synced readings"""
    storage.initialize()

    # Store old synced reading (35 days ago)
    old_timestamp = int(time.time()) - (35 * 24 * 3600)
    old_reading = Reading(
        timestamp=old_timestamp,
        sensor_channel=0,
        sensor_type="capacitive",
        raw_value=475,
        moisture_percent=65.5,
        location="test",
        plant_type="test",
        sensor_name="test"
    )
    old_id = storage.store_reading(old_reading)
    storage.mark_synced([old_id])

    # Store recent synced reading
    recent_reading = Reading(
        timestamp=int(time.time()),
        sensor_channel=0,
        sensor_type="capacitive",
        raw_value=480,
        moisture_percent=66.0,
        location="test",
        plant_type="test",
        sensor_name="test"
    )
    recent_id = storage.store_reading(recent_reading)
    storage.mark_synced([recent_id])

    # Cleanup (default 30 days)
    deleted_count = storage.cleanup_old_synced(days=30)

    assert deleted_count == 1

    # Verify old reading deleted, recent remains
    all_readings = storage.conn.execute("SELECT COUNT(*) FROM readings").fetchone()[0]
    assert all_readings == 1


def test_get_metadata(storage):
    """Test metadata storage"""
    storage.initialize()

    storage.set_metadata("agent_token", "test_token_123")
    storage.set_metadata("last_sync", "2026-02-15T10:00:00Z")

    assert storage.get_metadata("agent_token") == "test_token_123"
    assert storage.get_metadata("last_sync") == "2026-02-15T10:00:00Z"
    assert storage.get_metadata("nonexistent") is None
```

**Step 2: Run test to verify it fails**

Run: `cd pi-agent && pytest tests/test_storage.py -v`

Expected: FAIL with "ModuleNotFoundError: No module named 'storage'"

**Step 3: Implement storage module**

Create `pi-agent/storage.py`:
```python
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
```

**Step 4: Run test to verify it passes**

Run: `cd pi-agent && pytest tests/test_storage.py -v`

Expected: PASS (all 7 tests)

**Step 5: Commit**

```bash
git add pi-agent/storage.py pi-agent/tests/test_storage.py
git commit -m "feat(agent): add SQLite storage layer with metadata support"
```

---

### Task 1.4: Sensor Data Collection

**Files:**
- Create: `pi-agent/collector.py`
- Create: `pi-agent/tests/test_collector.py`

**Step 1: Write failing test for sensor reading**

Create `pi-agent/tests/test_collector.py`:
```python
import pytest
from unittest.mock import Mock, MagicMock
from collector import SensorCollector, calculate_moisture_percent
from config import SensorConfig, SensorCalibration, SensorLabels, SensorThresholds


def test_calculate_moisture_capacitive():
    """Test moisture calculation for capacitive sensors (inverted)"""
    # Capacitive: lower raw value = wetter
    # min=300 (wet), max=800 (dry)

    assert calculate_moisture_percent(300, 300, 800, sensor_type="capacitive") == 100.0  # Wet
    assert calculate_moisture_percent(800, 300, 800, sensor_type="capacitive") == 0.0    # Dry
    assert calculate_moisture_percent(550, 300, 800, sensor_type="capacitive") == 50.0   # Middle


def test_calculate_moisture_resistive():
    """Test moisture calculation for resistive sensors (normal)"""
    # Resistive: higher raw value = wetter
    # min=0 (dry), max=950 (wet)

    assert calculate_moisture_percent(0, 0, 950, sensor_type="resistive") == 0.0      # Dry
    assert calculate_moisture_percent(950, 0, 950, sensor_type="resistive") == 100.0  # Wet
    assert calculate_moisture_percent(475, 0, 950, sensor_type="resistive") == 50.0   # Middle


def test_calculate_moisture_clamps_values():
    """Test moisture percentage is clamped to 0-100"""
    # Out of range values should be clamped
    assert calculate_moisture_percent(900, 300, 800, sensor_type="capacitive") == 0.0
    assert calculate_moisture_percent(200, 300, 800, sensor_type="capacitive") == 100.0


@pytest.fixture
def mock_adc():
    """Mock ADC for testing"""
    adc = Mock()
    adc.read = Mock(return_value=475)
    return adc


@pytest.fixture
def sensor_config():
    """Sample sensor configuration"""
    return SensorConfig(
        channel=0,
        type="capacitive",
        calibration=SensorCalibration(min=300, max=800),
        labels=SensorLabels(
            location="greenhouse",
            plant_type="tomato",
            sensor_name="tomato-01"
        ),
        thresholds=SensorThresholds(
            dry_percent=30,
            wet_percent=85,
            hysteresis=5
        )
    )


def test_sensor_collector_read_success(mock_adc, sensor_config):
    """Test successful sensor reading"""
    collector = SensorCollector(mock_adc, sensor_config)

    reading = collector.read()

    assert reading is not None
    assert reading.sensor_channel == 0
    assert reading.sensor_type == "capacitive"
    assert reading.raw_value == 475
    assert 0 <= reading.moisture_percent <= 100
    assert reading.location == "greenhouse"
    assert reading.plant_type == "tomato"
    assert reading.sensor_name == "tomato-01"


def test_sensor_collector_read_retry_on_failure(sensor_config):
    """Test retry logic when sensor read fails"""
    mock_adc = Mock()
    mock_adc.read = Mock(side_effect=[None, None, 450])  # Fail twice, then succeed

    collector = SensorCollector(mock_adc, sensor_config)
    reading = collector.read()

    assert reading is not None
    assert reading.raw_value == 450
    assert mock_adc.read.call_count == 3


def test_sensor_collector_read_returns_none_after_retries(sensor_config):
    """Test returns None after max retries"""
    mock_adc = Mock()
    mock_adc.read = Mock(return_value=None)  # Always fail

    collector = SensorCollector(mock_adc, sensor_config)
    reading = collector.read()

    assert reading is None
    assert mock_adc.read.call_count == 3  # Max retries
```

**Step 2: Run test to verify it fails**

Run: `cd pi-agent && pytest tests/test_collector.py -v`

Expected: FAIL with "ModuleNotFoundError: No module named 'collector'"

**Step 3: Implement collector module**

Create `pi-agent/collector.py`:
```python
import time
import logging
from typing import Optional
from config import SensorConfig
from storage import Reading


logger = logging.getLogger(__name__)


def calculate_moisture_percent(
    raw_value: int,
    sensor_min: int,
    sensor_max: int,
    sensor_type: str
) -> float:
    """
    Calculate moisture percentage from raw ADC value.

    Capacitive sensors: Lower value = wetter (inverted)
    Resistive sensors: Higher value = wetter (normal)
    """
    if sensor_type == "capacitive":
        # Inverted: higher raw value = drier
        percentage = ((sensor_max - raw_value) / (sensor_max - sensor_min)) * 100
    else:  # resistive
        # Normal: higher raw value = wetter
        percentage = ((raw_value - sensor_min) / (sensor_max - sensor_min)) * 100

    # Clamp to 0-100
    return max(0.0, min(100.0, percentage))


class SensorCollector:
    def __init__(self, adc, sensor_config: SensorConfig):
        """
        Initialize sensor collector.

        Args:
            adc: ADC instance from grove.py (grove.adc.ADC)
            sensor_config: Sensor configuration
        """
        self.adc = adc
        self.config = sensor_config
        self.max_retries = 3
        self.retry_delay = 1  # seconds

    def read(self) -> Optional[Reading]:
        """
        Read sensor and return Reading object, or None if failed.

        Implements retry logic for transient failures.
        """
        raw_value = None

        # Retry logic
        for attempt in range(self.max_retries):
            try:
                raw_value = self.adc.read(self.config.channel)

                if raw_value is not None:
                    break

                logger.warning(
                    f"Sensor read attempt {attempt + 1} returned None "
                    f"(channel {self.config.channel})"
                )

            except Exception as e:
                logger.warning(
                    f"Sensor read attempt {attempt + 1} failed "
                    f"(channel {self.config.channel}): {e}"
                )

            if attempt < self.max_retries - 1:
                time.sleep(self.retry_delay)

        # All retries failed
        if raw_value is None:
            logger.error(
                f"Sensor {self.config.channel} offline or not responding "
                f"after {self.max_retries} attempts"
            )
            return None

        # Calculate moisture percentage
        moisture_percent = calculate_moisture_percent(
            raw_value,
            self.config.calibration.min,
            self.config.calibration.max,
            self.config.type
        )

        # Create reading
        reading = Reading(
            timestamp=int(time.time()),
            sensor_channel=self.config.channel,
            sensor_type=self.config.type,
            raw_value=raw_value,
            moisture_percent=moisture_percent,
            location=self.config.labels.location,
            plant_type=self.config.labels.plant_type,
            sensor_name=self.config.labels.sensor_name,
            synced=False
        )

        return reading
```

**Step 4: Run test to verify it passes**

Run: `cd pi-agent && pytest tests/test_collector.py -v`

Expected: PASS (all 6 tests)

**Step 5: Commit**

```bash
git add pi-agent/collector.py pi-agent/tests/test_collector.py
git commit -m "feat(agent): add sensor data collection with retry logic"
```

---

## Phase 2: Pi Agent - Network Communication

### Task 2.1: Agent Registration & Authentication

**Files:**
- Create: `pi-agent/registration.py`
- Create: `pi-agent/tests/test_registration.py`

**Step 1: Write failing test for registration**

Create `pi-agent/tests/test_registration.py`:
```python
import pytest
from unittest.mock import Mock, AsyncMock, patch
from registration import RegistrationClient, RegistrationError


@pytest.mark.asyncio
async def test_register_success():
    """Test successful agent registration"""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json = Mock(return_value={
        "agent_token": "agt_abc123",
        "config": {"version": 1}
    })

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)

    reg_client = RegistrationClient(
        orchestrator_url="https://orch.example.com",
        agent_id="pi-test-01",
        bootstrap_token="bst_xyz789"
    )
    reg_client.client = mock_client

    result = await reg_client.register(
        hostname="raspberrypi",
        hardware="Pi Zero 2 W"
    )

    assert result["agent_token"] == "agt_abc123"
    assert result["config"]["version"] == 1

    # Verify request
    mock_client.post.assert_called_once()
    call_args = mock_client.post.call_args
    assert "agents/register" in call_args[0][0]
    assert call_args[1]["headers"]["Authorization"] == "Bearer bst_xyz789"


@pytest.mark.asyncio
async def test_register_invalid_bootstrap_token():
    """Test registration fails with invalid bootstrap token"""
    mock_response = Mock()
    mock_response.status_code = 401
    mock_response.text = "Invalid bootstrap token"

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)

    reg_client = RegistrationClient(
        orchestrator_url="https://orch.example.com",
        agent_id="pi-test-01",
        bootstrap_token="invalid_token"
    )
    reg_client.client = mock_client

    with pytest.raises(RegistrationError, match="401"):
        await reg_client.register(hostname="test", hardware="test")


@pytest.mark.asyncio
async def test_register_network_error():
    """Test registration handles network errors"""
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(side_effect=Exception("Network unreachable"))

    reg_client = RegistrationClient(
        orchestrator_url="https://orch.example.com",
        agent_id="pi-test-01",
        bootstrap_token="bst_xyz789"
    )
    reg_client.client = mock_client

    with pytest.raises(RegistrationError, match="Network"):
        await reg_client.register(hostname="test", hardware="test")


@pytest.mark.asyncio
async def test_heartbeat():
    """Test sending heartbeat to orchestrator"""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json = Mock(return_value={"status": "ok"})

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)

    reg_client = RegistrationClient(
        orchestrator_url="https://orch.example.com",
        agent_id="pi-test-01",
        bootstrap_token="",
        agent_token="agt_abc123"
    )
    reg_client.client = mock_client

    await reg_client.heartbeat()

    # Verify request
    mock_client.post.assert_called_once()
    call_args = mock_client.post.call_args
    assert "pi-test-01/heartbeat" in call_args[0][0]
    assert call_args[1]["headers"]["Authorization"] == "Bearer agt_abc123"
```

**Step 2: Run test to verify it fails**

Run: `cd pi-agent && pytest tests/test_registration.py -v`

Expected: FAIL with "ModuleNotFoundError: No module named 'registration'"

**Step 3: Implement registration module**

Create `pi-agent/registration.py`:
```python
import logging
from typing import Dict, Any, Optional
import httpx


logger = logging.getLogger(__name__)


class RegistrationError(Exception):
    """Raised when agent registration fails"""
    pass


class RegistrationClient:
    def __init__(
        self,
        orchestrator_url: str,
        agent_id: str,
        bootstrap_token: Optional[str] = None,
        agent_token: Optional[str] = None,
        timeout: int = 30
    ):
        """
        Initialize registration client.

        Args:
            orchestrator_url: Base URL of orchestrator
            agent_id: Unique agent identifier
            bootstrap_token: Bootstrap token for initial registration
            agent_token: Permanent agent token (if already registered)
            timeout: Request timeout in seconds
        """
        self.orchestrator_url = orchestrator_url.rstrip('/')
        self.agent_id = agent_id
        self.bootstrap_token = bootstrap_token
        self.agent_token = agent_token
        self.timeout = timeout

        self.client = httpx.AsyncClient(timeout=timeout)

    async def register(self, hostname: str, hardware: str) -> Dict[str, Any]:
        """
        Register agent with orchestrator using bootstrap token.

        Returns:
            Registration response with agent_token and config

        Raises:
            RegistrationError: If registration fails
        """
        if not self.bootstrap_token:
            raise RegistrationError("Bootstrap token required for registration")

        url = f"{self.orchestrator_url}/agents/register"
        headers = {"Authorization": f"Bearer {self.bootstrap_token}"}
        payload = {
            "agent_id": self.agent_id,
            "hostname": hostname,
            "hardware": hardware
        }

        try:
            logger.info(f"Registering agent {self.agent_id} with orchestrator")
            response = await self.client.post(url, json=payload, headers=headers)

            if response.status_code == 200:
                data = response.json()
                logger.info("Agent registration successful")
                return data
            else:
                error_msg = f"Registration failed with status {response.status_code}: {response.text}"
                logger.error(error_msg)
                raise RegistrationError(error_msg)

        except httpx.HTTPError as e:
            error_msg = f"Network error during registration: {e}"
            logger.error(error_msg)
            raise RegistrationError(error_msg)

    async def heartbeat(self) -> Dict[str, Any]:
        """
        Send heartbeat to orchestrator.

        Returns:
            Heartbeat response

        Raises:
            RegistrationError: If heartbeat fails
        """
        if not self.agent_token:
            raise RegistrationError("Agent token required for heartbeat")

        url = f"{self.orchestrator_url}/agents/{self.agent_id}/heartbeat"
        headers = {"Authorization": f"Bearer {self.agent_token}"}

        try:
            response = await self.client.post(url, headers=headers)

            if response.status_code == 200:
                return response.json()
            else:
                error_msg = f"Heartbeat failed with status {response.status_code}"
                logger.warning(error_msg)
                raise RegistrationError(error_msg)

        except httpx.HTTPError as e:
            logger.warning(f"Heartbeat network error: {e}")
            raise RegistrationError(str(e))

    async def close(self):
        """Close HTTP client"""
        await self.client.aclose()
```

**Step 4: Run test to verify it passes**

Run: `cd pi-agent && pytest tests/test_registration.py -v`

Expected: PASS (all 4 tests)

**Step 5: Commit**

```bash
git add pi-agent/registration.py pi-agent/tests/test_registration.py
git commit -m "feat(agent): add registration and heartbeat client"
```

---

Due to character limits, I'll continue with a summary of remaining tasks. The full implementation plan would continue with:

**Phase 2 (continued):**
- Task 2.2: Data Sync to Orchestrator
- Task 2.3: Config Pull from Orchestrator

**Phase 3: Pi Agent - API Server & Scheduler**
- Task 3.1: FastAPI Local Management API
- Task 3.2: APScheduler Integration
- Task 3.3: Main Agent Service

**Phase 4: Orchestrator Service**
- Task 4.1: Database Models & Setup
- Task 4.2: Agent Registration Endpoints
- Task 4.3: Data Ingestion & InfluxDB Writer
- Task 4.4: Alert Calculation Engine
- Task 4.5: Config Management

**Phase 5: API Server**
- Task 5.1: InfluxDB Query Layer
- Task 5.2: Homepage API Endpoints
- Task 5.3: Caching Layer

**Phase 6: Deployment**
- Task 6.1: Pi Agent Installation Script
- Task 6.2: Kubernetes Manifests
- Task 6.3: Helm Charts for Databases

**Phase 7: Testing & Documentation**
- Task 7.1: Integration Tests
- Task 7.2: End-to-End Tests
- Task 7.3: Deployment Documentation

Each task follows the same TDD pattern with 5 steps per task.

Would you like me to expand any specific phase or continue with the detailed task breakdowns?
