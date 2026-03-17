# Stuck Sensor Detection Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Detect when a sensor's raw ADC value stops varying meaningfully, flag affected readings as `stuck=True`, and create a `sensor_stuck` alert in the orchestrator so the user knows the sensor needs investigation.

**Architecture:** An in-memory ring buffer (deque) in `SensorCollector` tracks recent raw values. When the window fills and the spread is below a configurable threshold, the reading is flagged. The flag flows through the existing SQLite → sync → orchestrator pipeline; the orchestrator creates/resolves a `sensor_stuck` PostgreSQL alert and wires up the previously-dormant threshold alert logic as a byproduct.

**Tech Stack:** Python, Pydantic v2, SQLite (pi-agent), FastAPI + SQLAlchemy + PostgreSQL (orchestrator), pytest

---

## Chunk 1: Pi-Agent — Config, Detection, Storage

### Task 1: Add `StuckDetectionConfig` to sensor config

**Files:**
- Modify: `pi-agent/config.py`
- Modify: `pi-agent/tests/test_config.py`

- [ ] **Step 1: Write the failing test**

Add to `pi-agent/tests/test_config.py`:

```python
def test_stuck_detection_defaults():
    """StuckDetectionConfig has sensible defaults and is optional in SensorConfig."""
    from config import SensorConfig, StuckDetectionConfig
    cfg = StuckDetectionConfig()
    assert cfg.enabled is True
    assert cfg.window_readings == 30
    assert cfg.min_range == 10


def test_stuck_detection_custom():
    from config import StuckDetectionConfig
    cfg = StuckDetectionConfig(enabled=False, window_readings=60, min_range=5)
    assert cfg.enabled is False
    assert cfg.window_readings == 60
    assert cfg.min_range == 5


def test_stuck_detection_validation():
    import pytest
    from config import StuckDetectionConfig
    with pytest.raises(Exception):
        StuckDetectionConfig(window_readings=4)   # below ge=5
    with pytest.raises(Exception):
        StuckDetectionConfig(window_readings=241)  # above le=240
    with pytest.raises(Exception):
        StuckDetectionConfig(min_range=0)          # below ge=1


def test_sensor_config_stuck_detection_optional(sample_sensor_config_data):
    """Existing sensor configs without stuck_detection still load fine."""
    from config import SensorConfig
    cfg = SensorConfig(**sample_sensor_config_data)
    assert cfg.stuck_detection.enabled is True   # default
```

Add this fixture at the top of the test file (the file does not already have it):

```python
@pytest.fixture
def sample_sensor_config_data():
    return {
        "channel": 0, "type": "capacitive",
        "calibration": {"min": 300, "max": 800},
        "labels": {"location": "Room A", "plant_type": "Fern", "sensor_name": "A0"},
        "thresholds": {"dry_percent": 30, "wet_percent": 85}
    }
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd pi-agent && python -m pytest tests/test_config.py -k "stuck" -v
```

Expected: `ImportError` or `AttributeError` — `StuckDetectionConfig` not found yet.

- [ ] **Step 3: Implement `StuckDetectionConfig` in `config.py`**

Add after `SensorThresholds`:

```python
class StuckDetectionConfig(BaseModel):
    enabled: bool = True
    window_readings: int = Field(default=30, ge=5, le=240)
    min_range: int = Field(default=10, ge=1, le=500)
```

Add to `SensorConfig`:

```python
stuck_detection: StuckDetectionConfig = StuckDetectionConfig()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd pi-agent && python -m pytest tests/test_config.py -k "stuck" -v
```

Expected: all 4 tests PASS.

- [ ] **Step 5: Run full config test suite to check for regressions**

```bash
cd pi-agent && python -m pytest tests/test_config.py -v
```

Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add pi-agent/config.py pi-agent/tests/test_config.py
git commit -m "feat(pi-agent): add StuckDetectionConfig to SensorConfig"
```

---

### Task 2: Add `stuck` field to `Reading` and update SQLite storage

**Files:**
- Modify: `pi-agent/storage.py`

- [ ] **Step 1: Write the failing tests**

Create `pi-agent/tests/test_storage.py` (or add to it if it exists):

```python
import sqlite3
import tempfile
import os
import pytest
from storage import StorageManager, Reading


@pytest.fixture
def db(tmp_path):
    mgr = StorageManager(str(tmp_path / "test.db"))
    mgr.initialize()
    yield mgr
    mgr.close()


def make_reading(**kwargs):
    defaults = dict(
        timestamp=1000000, sensor_channel=0, sensor_type="capacitive",
        raw_value=1500, moisture_percent=80.0,
        location="Room A", plant_type="Fern", sensor_name="A0", synced=False
    )
    defaults.update(kwargs)
    return Reading(**defaults)


def test_reading_has_stuck_field():
    r = make_reading()
    assert r.stuck is False


def test_reading_stuck_true():
    r = make_reading(stuck=True)
    assert r.stuck is True


def test_store_and_retrieve_stuck_false(db):
    r = make_reading(stuck=False)
    db.store_reading(r)
    rows = db.get_unsynced_readings()
    assert rows[0]["stuck"] == 0  # SQLite stores bool as int


def test_store_and_retrieve_stuck_true(db):
    r = make_reading(stuck=True)
    db.store_reading(r)
    rows = db.get_unsynced_readings()
    assert rows[0]["stuck"] == 1


def test_migration_idempotent(tmp_path):
    """Calling initialize() twice does not raise (column already exists)."""
    mgr = StorageManager(str(tmp_path / "test.db"))
    mgr.initialize()
    mgr.initialize()   # should not raise
    mgr.close()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd pi-agent && python -m pytest tests/test_storage.py -v
```

Expected: `TypeError` — `Reading.__init__` has no `stuck` parameter.

- [ ] **Step 3: Add `stuck` to `Reading` dataclass**

In `storage.py`, add to `Reading` after `synced`:

```python
stuck: bool = False
```

- [ ] **Step 4: Add SQLite migration and update `store_reading()`**

In `StorageManager.initialize()`, after `self.conn.commit()` at the end:

```python
# Migrate: add stuck column if not present (safe to run on every startup)
try:
    self.conn.execute("ALTER TABLE readings ADD COLUMN stuck BOOLEAN DEFAULT 0")
    self.conn.commit()
except sqlite3.OperationalError:
    pass  # column already exists
```

In `store_reading()`, update the INSERT:

```python
cursor = self.conn.execute("""
    INSERT INTO readings (
        timestamp, sensor_channel, sensor_type, raw_value,
        moisture_percent, location, plant_type, sensor_name, synced, stuck
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
""", (
    reading.timestamp,
    reading.sensor_channel,
    reading.sensor_type,
    reading.raw_value,
    reading.moisture_percent,
    reading.location,
    reading.plant_type,
    reading.sensor_name,
    reading.synced,
    reading.stuck,
))
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd pi-agent && python -m pytest tests/test_storage.py -v
```

Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add pi-agent/storage.py pi-agent/tests/test_storage.py
git commit -m "feat(pi-agent): add stuck field to Reading and SQLite storage"
```

---

### Task 3: Stuck detection in `SensorCollector`

**Files:**
- Modify: `pi-agent/collector.py`
- Modify: `pi-agent/tests/test_collector.py`

- [ ] **Step 1: Write the failing tests**

Add the following imports at the top of `pi-agent/tests/test_collector.py` (alongside existing imports):

```python
from unittest.mock import MagicMock
from config import SensorConfig, StuckDetectionConfig
```

Then add the test functions:

```python


def make_sensor_config(window_readings=5, min_range=10, enabled=True):
    return SensorConfig(
        channel=0, type="capacitive",
        calibration={"min": 300, "max": 800},
        labels={"location": "Room A", "plant_type": "Fern", "sensor_name": "A0"},
        thresholds={"dry_percent": 30, "wet_percent": 85},
        stuck_detection=StuckDetectionConfig(
            enabled=enabled,
            window_readings=window_readings,
            min_range=min_range
        )
    )


def make_collector(window_readings=5, min_range=10, enabled=True):
    from collector import SensorCollector
    cfg = make_sensor_config(window_readings=window_readings, min_range=min_range, enabled=enabled)
    adc = MagicMock()
    return SensorCollector(adc, cfg)


def test_window_not_full_no_stuck_flag():
    """Sensor not flagged stuck until window is full."""
    collector = make_collector(window_readings=5)
    collector.adc.read.return_value = 500  # constant value
    for _ in range(4):  # one short of full
        reading = collector.read()
        assert reading.stuck is False


def test_window_full_low_range_flags_stuck():
    """When window is full and range < min_range, reading is stuck."""
    collector = make_collector(window_readings=5, min_range=10)
    collector.adc.read.return_value = 500  # constant — range = 0
    for _ in range(4):
        collector.read()
    reading = collector.read()  # 5th read fills window
    assert reading.stuck is True


def test_window_full_sufficient_range_not_stuck():
    """When window is full but range >= min_range, reading is not stuck."""
    collector = make_collector(window_readings=5, min_range=10)
    values = [500, 510, 520, 530, 540]  # range = 40 > 10
    collector.adc.read.side_effect = values
    readings = [collector.read() for _ in range(5)]
    assert readings[-1].stuck is False


def test_stuck_detection_disabled():
    """When enabled=False, never flags stuck even with constant raw value."""
    collector = make_collector(window_readings=5, min_range=10, enabled=False)
    collector.adc.read.return_value = 500
    for _ in range(10):
        reading = collector.read()
        assert reading.stuck is False


def test_stuck_then_unstuck():
    """After being stuck, sensor recovers when values start varying."""
    collector = make_collector(window_readings=5, min_range=10)
    # Fill window with constant values → stuck
    collector.adc.read.return_value = 500
    for _ in range(5):
        collector.read()
    stuck_reading = collector.read()
    assert stuck_reading.stuck is True

    # Now values start varying
    collector.adc.read.side_effect = [500, 510, 520, 530, 540, 550]
    readings = [collector.read() for _ in range(6)]
    # After enough varying readings fill the window, no longer stuck
    assert readings[-1].stuck is False
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd pi-agent && python -m pytest tests/test_collector.py -k "stuck" -v
```

Expected: `AttributeError` or `TypeError` — `SensorCollector` has no `_raw_window`.

- [ ] **Step 3: Implement stuck detection in `SensorCollector`**

In `collector.py`, add `from collections import deque` at the top.

In `SensorCollector.__init__`, add after `self.retry_delay = 1`:

```python
self._raw_window: deque = deque(maxlen=self.config.stuck_detection.window_readings)
```

In `SensorCollector.read()`, after calculating `moisture_percent` and before creating the `Reading`, add:

```python
# Stuck detection
self._raw_window.append(raw_value)
stuck = False
cfg = self.config.stuck_detection
if (
    cfg.enabled
    and len(self._raw_window) == self._raw_window.maxlen
    and (max(self._raw_window) - min(self._raw_window)) < cfg.min_range
):
    stuck = True
    logger.warning(
        f"Sensor {self.config.channel} ({self.config.labels.sensor_name}) appears stuck: "
        f"raw range={max(self._raw_window) - min(self._raw_window)} ADC counts "
        f"over {len(self._raw_window)} readings (threshold: {cfg.min_range})"
    )
```

Update the `Reading(...)` constructor call to pass `stuck=stuck`.

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd pi-agent && python -m pytest tests/test_collector.py -v
```

Expected: all tests PASS.

> **Note:** There is a pre-existing bug where `test_calculate_moisture_resistive_inverted` may already
> be failing — the `calculate_moisture_percent` function doesn't have an explicit `resistive_inverted`
> branch, so it falls into the resistive `else` path and gives wrong results. If this test is failing
> before you start, it is not caused by your changes. Fix it by adding a `resistive_inverted` branch
> to `calculate_moisture_percent` that uses the capacitive formula: `((sensor_max - raw_value) / span) * 100`.
> This is a one-line addition to the if/elif/else chain.

- [ ] **Step 5: Commit**

```bash
git add pi-agent/collector.py pi-agent/tests/test_collector.py
git commit -m "feat(pi-agent): detect stuck sensors using raw value ring buffer"
```

---

## Chunk 2: Orchestrator — Alert Engine + Ingestion

### Task 4: Add `check_stuck` / `resolve_stuck` to `AlertEngine`

**Files:**
- Modify: `orchestrator/alerts.py`
- Create: `orchestrator/tests/test_alerts_stuck.py`

Background on the existing code:
- `AlertEngine._create_alert()` currently types `moisture_percent` and `threshold` as `float` — but `ActiveAlert` in `models.py` has both columns as `nullable=True`. We need to relax those to `Optional[float]` to support `sensor_stuck` alerts that have no moisture reading.
- `AlertEngine.check_reading()` queries `ActiveAlert` without filtering by `alert_type`. A live `sensor_stuck` alert would block `too_dry`/`too_wet` creation. The if/else ordering in Task 5 prevents this — `check_reading()` is only called when the sensor is not stuck.

- [ ] **Step 1: Check for existing orchestrator test directory**

```bash
ls orchestrator/tests/ 2>/dev/null || echo "no tests dir yet — create orchestrator/tests/__init__.py"
```

If the directory doesn't exist, create it:
```bash
mkdir -p orchestrator/tests && touch orchestrator/tests/__init__.py
```

- [ ] **Step 2: Write the failing tests**

Create `orchestrator/tests/test_alerts_stuck.py`:

```python
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import Base, ActiveAlert
from alerts import AlertEngine


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_check_stuck_creates_alert(db_session):
    engine = AlertEngine(db_session)
    engine.check_stuck("agent-1", 0, "Room A", "Fern", "A0")
    alert = db_session.query(ActiveAlert).filter_by(
        agent_id="agent-1", sensor_channel=0, alert_type="sensor_stuck"
    ).first()
    assert alert is not None
    assert alert.resolved_at is None
    assert alert.moisture_percent is None   # sensor_stuck has no moisture value
    assert alert.threshold is None


def test_check_stuck_idempotent(db_session):
    """Calling check_stuck twice creates only one alert."""
    engine = AlertEngine(db_session)
    engine.check_stuck("agent-1", 0, "Room A", "Fern", "A0")
    engine.check_stuck("agent-1", 0, "Room A", "Fern", "A0")
    count = db_session.query(ActiveAlert).filter_by(
        agent_id="agent-1", sensor_channel=0, alert_type="sensor_stuck",
        resolved_at=None
    ).count()
    assert count == 1


def test_resolve_stuck_resolves_alert(db_session):
    engine = AlertEngine(db_session)
    engine.check_stuck("agent-1", 0, "Room A", "Fern", "A0")
    engine.resolve_stuck("agent-1", 0)
    alert = db_session.query(ActiveAlert).filter_by(
        agent_id="agent-1", sensor_channel=0, alert_type="sensor_stuck"
    ).first()
    assert alert.resolved_at is not None


def test_resolve_stuck_no_alert_is_noop(db_session):
    """resolve_stuck when no alert exists does not raise."""
    engine = AlertEngine(db_session)
    engine.resolve_stuck("agent-1", 0)  # should not raise
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
cd orchestrator && python -m pytest tests/test_alerts_stuck.py -v
```

Expected: `AttributeError` — `AlertEngine` has no `check_stuck`.

- [ ] **Step 4: Update `_create_alert` signature and implement `check_stuck` / `resolve_stuck`**

In `orchestrator/alerts.py`, `Optional` is already imported — no import change needed.

Update the `_create_alert` method signature and its log line to handle `None` values:

```python
def _create_alert(
    self,
    agent_id: str,
    sensor_channel: int,
    alert_type: str,
    moisture_percent: Optional[float],
    threshold: Optional[float],
    location: str,
    plant_type: str,
    sensor_name: str,
):
    """Create a new alert"""
    alert = ActiveAlert(
        agent_id=agent_id,
        sensor_channel=sensor_channel,
        alert_type=alert_type,
        moisture_percent=moisture_percent,
        threshold=threshold,
        location=location,
        plant_type=plant_type,
        sensor_name=sensor_name
    )

    self.db.add(alert)
    self.db.commit()

    pct_str = f"{moisture_percent:.1f}%" if moisture_percent is not None else "N/A"
    thr_str = f"{threshold}%" if threshold is not None else "N/A"
    logger.warning(
        f"Alert triggered: {alert_type} for {agent_id}/channel-{sensor_channel} "
        f"({sensor_name}): {pct_str} (threshold: {thr_str})"
    )
```

Then add `check_stuck` and `resolve_stuck` after `_resolve_alert`:

```python
def check_stuck(
    self,
    agent_id: str,
    sensor_channel: int,
    location: str,
    plant_type: str,
    sensor_name: str,
):
    """Create sensor_stuck alert if one does not already exist."""
    existing = self.db.query(ActiveAlert).filter(
        ActiveAlert.agent_id == agent_id,
        ActiveAlert.sensor_channel == sensor_channel,
        ActiveAlert.alert_type == "sensor_stuck",
        ActiveAlert.resolved_at.is_(None)
    ).first()
    if not existing:
        self._create_alert(
            agent_id=agent_id,
            sensor_channel=sensor_channel,
            alert_type="sensor_stuck",
            moisture_percent=None,
            threshold=None,
            location=location,
            plant_type=plant_type,
            sensor_name=sensor_name,
        )

def resolve_stuck(self, agent_id: str, sensor_channel: int):
    """Resolve sensor_stuck alert when sensor starts varying again."""
    alert = self.db.query(ActiveAlert).filter(
        ActiveAlert.agent_id == agent_id,
        ActiveAlert.sensor_channel == sensor_channel,
        ActiveAlert.alert_type == "sensor_stuck",
        ActiveAlert.resolved_at.is_(None)
    ).first()
    if alert:
        self._resolve_alert(alert)
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd orchestrator && python -m pytest tests/test_alerts_stuck.py -v
```

Expected: all 4 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add orchestrator/alerts.py orchestrator/tests/
git commit -m "feat(orchestrator): add check_stuck/resolve_stuck to AlertEngine"
```

---

### Task 5: Wire up alert checking in ingestion

**Files:**
- Modify: `orchestrator/ingestion.py`
- Modify: `orchestrator/tests/test_alerts_stuck.py`

**How threshold lookup works:** Thresholds are stored in `AgentConfig.config_data` (a JSON column) as
`config_data["sensors"][n]["thresholds"]` — a dict with `dry_percent`, `wet_percent`, `hysteresis`.
We find the matching sensor by `channel`. The `Agent` object (already in scope via `Depends(verify_agent_token)`)
provides `desired_config_version` to find the current config row.

**Alert error handling:** Alert processing must not fail the HTTP response if it errors. Wrap in
try/except and log — the InfluxDB write has already succeeded by this point.

- [ ] **Step 1: Write the failing integration test**

Add to `orchestrator/tests/test_alerts_stuck.py`:

```python
from ingestion import _get_sensor_thresholds
from models import Agent, AgentConfig


def test_get_sensor_thresholds_found(db_session):
    """_get_sensor_thresholds returns thresholds dict for a known sensor."""
    # Set up an agent and config in the test DB
    agent = Agent(
        agent_id="agent-1",
        agent_token_hash="x",
        desired_config_version=1,
        applied_config_version=0,
    )
    db_session.add(agent)
    config = AgentConfig(
        agent_id="agent-1",
        version=1,
        config_data={
            "sensors": [
                {
                    "channel": 0,
                    "thresholds": {"dry_percent": 25.0, "wet_percent": 80.0, "hysteresis": 5.0}
                }
            ]
        }
    )
    db_session.add(config)
    db_session.commit()

    result = _get_sensor_thresholds(db_session, agent, 0)
    assert result == {"dry_percent": 25.0, "wet_percent": 80.0, "hysteresis": 5.0}


def test_get_sensor_thresholds_not_found(db_session):
    """_get_sensor_thresholds returns None when sensor channel not in config."""
    agent = Agent(
        agent_id="agent-2",
        agent_token_hash="x",
        desired_config_version=1,
        applied_config_version=0,
    )
    db_session.add(agent)
    config = AgentConfig(
        agent_id="agent-2", version=1,
        config_data={"sensors": [{"channel": 2, "thresholds": {}}]}
    )
    db_session.add(config)
    db_session.commit()

    result = _get_sensor_thresholds(db_session, agent, 0)  # channel 0 not in config
    assert result is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd orchestrator && python -m pytest tests/test_alerts_stuck.py -k "thresholds" -v
```

Expected: `ImportError` — `_get_sensor_thresholds` not in `ingestion` yet.

- [ ] **Step 3: Update imports and add helpers at module level in `ingestion.py`**

Replace the existing `from typing import List` line with:

```python
from typing import List, Optional, Dict
```

Replace `from models import Agent` (the existing import) with:

```python
from models import Agent, AgentConfig
```

Add alongside the other imports:

```python
from alerts import AlertEngine
```

- [ ] **Step 4: Add `_get_sensor_thresholds` helper to `ingestion.py`**

Add this module-level function before the router endpoints:

```python
def _get_sensor_thresholds(
    db: Session,
    agent: Agent,
    sensor_channel: int,
) -> Optional[Dict[str, float]]:
    """Look up thresholds for a sensor from the agent's current config."""
    config = db.query(AgentConfig).filter(
        AgentConfig.agent_id == agent.agent_id,
        AgentConfig.version == agent.desired_config_version
    ).first()
    if not config:
        return None
    for sensor in config.config_data.get("sensors", []):
        if sensor.get("channel") == sensor_channel:
            return sensor.get("thresholds")
    return None
```

- [ ] **Step 5: Run threshold tests to verify they pass**

```bash
cd orchestrator && python -m pytest tests/test_alerts_stuck.py -k "thresholds" -v
```

Expected: both threshold tests PASS.

- [ ] **Step 6: Wire alert processing into `upload_readings`**

Add `stuck: bool = False` to the `Reading` Pydantic model in `ingestion.py`:

```python
class Reading(BaseModel):
    timestamp: int
    sensor_channel: int
    sensor_type: str
    raw_value: int
    moisture_percent: float
    location: str
    plant_type: str
    sensor_name: str
    stuck: bool = False
```

In `upload_readings`, the existing try/except block ends with a `return UploadReadingsResponse(...)`.
Place the alert block **inside the existing try block, after `db.commit()` and before the `return`**,
with its own nested try/except so alert failures never propagate to the outer HTTP 500 handler:

```python
        db.commit()

        # Process alerts — nested try so failures log but don't fail the request
        try:
            alert_engine = AlertEngine(db)
            for r in request.readings:
                if r.stuck:
                    alert_engine.check_stuck(
                        agent_id=agent_id,
                        sensor_channel=r.sensor_channel,
                        location=r.location,
                        plant_type=r.plant_type,
                        sensor_name=r.sensor_name,
                    )
                else:
                    alert_engine.resolve_stuck(agent_id, r.sensor_channel)
                    thresholds = _get_sensor_thresholds(db, agent, r.sensor_channel)
                    if thresholds:
                        alert_engine.check_reading(
                            agent_id=agent_id,
                            sensor_channel=r.sensor_channel,
                            moisture_percent=r.moisture_percent,
                            location=r.location,
                            plant_type=r.plant_type,
                            sensor_name=r.sensor_name,
                            thresholds=thresholds,
                        )
        except Exception as alert_err:
            logger.error(f"Alert processing failed for {agent_id}: {alert_err}", exc_info=True)

        logger.info(f"Accepted {written} readings from {agent_id}")

        return UploadReadingsResponse(
            accepted=written,
            rejected=0,
            message=f"Successfully stored {written} readings"
        )
```

> **Note:** Remove the existing `logger.info(f"Accepted {written}...")` line that was before the
> `return` — it's included in the block above to preserve its position after alert processing.

- [ ] **Step 8: Add integration test for the ingestion wiring**

Add to `orchestrator/tests/test_alerts_stuck.py`:

```python
from ingestion import upload_readings, UploadReadingsRequest
from ingestion import Reading as IngestReading
from unittest.mock import patch, MagicMock


@pytest.mark.asyncio
async def test_upload_stuck_reading_via_endpoint_creates_alert(db_session):
    """POSTing a stuck reading to upload_readings creates a sensor_stuck alert."""
    agent = Agent(
        agent_id="agent-3",
        agent_token_hash="x",
        desired_config_version=1,
        applied_config_version=0,
    )
    db_session.add(agent)
    db_session.commit()

    request = UploadReadingsRequest(readings=[
        IngestReading(
            timestamp=1000000, sensor_channel=0, sensor_type="capacitive",
            raw_value=500, moisture_percent=99.0,
            location="Room A", plant_type="Fern", sensor_name="A0",
            stuck=True,
        )
    ])

    mock_influx = MagicMock()
    mock_influx.write_readings.return_value = 1

    with patch("ingestion.influx_writer", mock_influx):
        response = await upload_readings(
            agent_id="agent-3",
            request=request,
            agent=agent,
            db=db_session,
        )

    assert response.accepted == 1
    alert = db_session.query(ActiveAlert).filter_by(
        agent_id="agent-3", sensor_channel=0, alert_type="sensor_stuck",
        resolved_at=None
    ).first()
    assert alert is not None
```

If `pytest-asyncio` is not in the orchestrator's requirements, add it:

```bash
pip install pytest-asyncio
```

And ensure `pytest.ini` or `pyproject.toml` has `asyncio_mode = auto` or mark the test with
`@pytest.mark.asyncio`.

- [ ] **Step 9: Verify `stuck` flows through sync.py**

`sync.py`'s `SyncClient.sync_readings()` calls `storage.get_unsynced_readings()` (which returns `SELECT *`, so `stuck` is included) and strips only `id`, `synced`, and `created_at` from the payload before uploading. Confirm this is still true:

```bash
grep -n "k not in\|strip\|pop\|exclude" pi-agent/sync.py
```

Expected output includes: `if k not in ['id', 'synced', 'created_at']` — confirming `stuck` is included in the payload automatically. If the strip list has changed, add `stuck` to the explicitly kept fields.

- [ ] **Step 10: Run all orchestrator tests**

```bash
cd orchestrator && python -m pytest -v
```

Expected: all tests PASS.

- [ ] **Step 11: Commit**

```bash
git add orchestrator/ingestion.py orchestrator/tests/
git commit -m "feat(orchestrator): wire alert checking in ingestion, add sensor_stuck handling"
```

---

## Chunk 3: End-to-End Verification + Session Close

### Task 6: End-to-end smoke test and push

- [ ] **Step 1: Run the full pi-agent test suite**

```bash
cd pi-agent && python -m pytest -v
```

Expected: all tests PASS.

- [ ] **Step 2: Run the full orchestrator test suite**

```bash
cd orchestrator && python -m pytest -v
```

Expected: all tests PASS.

- [ ] **Step 3: Verify the stuck column exists in a real SQLite DB**

```bash
cd pi-agent && python -c "
from storage import StorageManager
import tempfile, os
with tempfile.TemporaryDirectory() as d:
    mgr = StorageManager(os.path.join(d, 'test.db'))
    mgr.initialize()
    import sqlite3
    conn = sqlite3.connect(os.path.join(d, 'test.db'))
    cols = [r[1] for r in conn.execute('PRAGMA table_info(readings)').fetchall()]
    print('Columns:', cols)
    assert 'stuck' in cols, 'stuck column missing!'
    print('OK: stuck column present')
    conn.close()
    mgr.close()
"
```

Expected: `OK: stuck column present`

- [ ] **Step 4: Verify stuck detection fires correctly end-to-end**

```bash
cd pi-agent && python -c "
from unittest.mock import MagicMock
from config import SensorConfig, StuckDetectionConfig
from collector import SensorCollector

cfg = SensorConfig(
    channel=0, type='capacitive',
    calibration={'min': 300, 'max': 800},
    labels={'location': 'Room A', 'plant_type': 'Fern', 'sensor_name': 'A0'},
    thresholds={'dry_percent': 30, 'wet_percent': 85},
    stuck_detection=StuckDetectionConfig(window_readings=5, min_range=10)
)
adc = MagicMock()
adc.read.return_value = 500
collector = SensorCollector(adc, cfg)

readings = [collector.read() for _ in range(5)]
print('stuck flags:', [r.stuck for r in readings])
assert readings[0].stuck is False   # window not full yet
assert readings[3].stuck is False   # window not full yet
assert readings[4].stuck is True    # window full (5 reads), range=0 < 10
print('OK: stuck detection works end-to-end')
"
```

Expected: `OK: stuck detection works end-to-end`

- [ ] **Step 5: Close the beads issue**

```bash
bd close raspi-moisture-sensor-igr --reason="Implemented stuck sensor detection in pi-agent and orchestrator"
```

- [ ] **Step 6: Push**

```bash
git pull --rebase
bd dolt push
git push
git status
```

Expected: `Your branch is up to date with 'origin/main'`
