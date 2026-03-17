# Stuck Sensor Detection — Design Spec

**Date:** 2026-03-16
**Issue:** raspi-moisture-sensor-igr
**Status:** Approved

## Problem

A capacitive sensor (A0) was observed reporting ~99–100% moisture for 7+ days straight while the plant
dried out completely. The raw ADC value was pegged at ~1580–1616 (calibration wet-point: min=1608)
with no variation. The collocated resistive sensor (A2) correctly tracked the plant drying from 39% → 0%.

Root cause: the sensor's conformal coating had failed, exposing copper traces that shorted the
capacitive measurement, causing it to read permanently wet. The system had no way to detect this.

## Goals

- Detect when a sensor's raw ADC value has not changed meaningfully over a configurable time window
- Flag affected readings as `stuck=True`
- Create a `sensor_stuck` alert in the orchestrator's PostgreSQL alert store
- Auto-resolve the alert when the sensor starts reporting meaningful variation again

## Out of Scope

- Server-side (InfluxDB) stuck detection — detection lives in the pi-agent only
- Dashboard UI changes for displaying stuck sensor warnings

## Architecture

Detection lives entirely in the **pi-agent** (`SensorCollector`), using an in-memory ring buffer.
Flagged readings flow to the **orchestrator** via the existing sync path, where alert creation/resolution
is handled. No new network endpoints or protocols needed.

## Design

### 1. Config (`pi-agent/config.py`)

New optional model nested into `SensorConfig`:

```python
class StuckDetectionConfig(BaseModel):
    enabled: bool = True
    window_readings: int = Field(default=30, ge=5, le=240)
    # Number of readings to track. At 1 reading/min, 30 = ~30 minutes.

    min_range: int = Field(default=10, ge=1, le=500)
    # Minimum ADC spread (max - min) over window to be considered "alive".
    # A healthy sensor in any soil will drift more than 10 counts over 30 minutes.
```

Added to `SensorConfig` with a default so existing configs require no changes:

```python
stuck_detection: StuckDetectionConfig = StuckDetectionConfig()
```

Example config override for a sensor in very stable conditions:

```yaml
stuck_detection:
  window_readings: 60   # 1 hour window
  min_range: 5          # tighter threshold
```

### 2. Detection Logic (`pi-agent/collector.py`)

`SensorCollector.__init__` gains a ring buffer sized to the configured window:

```python
from collections import deque
self._raw_window: deque = deque(maxlen=sensor_config.stuck_detection.window_readings)
```

After each successful read, the window is updated and evaluated:

```python
self._raw_window.append(raw_value)

cfg = self.config.stuck_detection
if (
    cfg.enabled
    and len(self._raw_window) == self._raw_window.maxlen
    and (max(self._raw_window) - min(self._raw_window)) < cfg.min_range
):
    reading.stuck = True
    logger.warning(
        f"Sensor {self.config.channel} ({self.config.labels.sensor_name}) appears stuck: "
        f"raw range={max(self._raw_window) - min(self._raw_window)} ADC counts "
        f"over {len(self._raw_window)} readings (threshold: {cfg.min_range})"
    )
```

Key properties:
- Detection only fires once the window is **full** — no false positives on startup or after config reload
- The deque resets automatically when `AgentScheduler.set_config()` rebuilds collectors after a config pull, which is acceptable — at most one window of delayed detection after a reload

### 3. Reading Model + Storage + Sync

**`pi-agent/storage.py`** — `Reading` dataclass:

```python
stuck: bool = False
```

SQLite schema migration in `StorageManager.initialize()`, safe to run on every startup:

```python
try:
    self.conn.execute("ALTER TABLE readings ADD COLUMN stuck BOOLEAN DEFAULT 0")
    self.conn.commit()
except sqlite3.OperationalError:
    pass  # column already exists
```

`store_reading()` includes `stuck` in the INSERT. `get_unsynced_readings()` returns it via `SELECT *`.
`SyncClient` already strips only `id`, `synced`, and `created_at` from the payload, so `stuck` flows
to the orchestrator with no changes to `sync.py`.

### 4. Orchestrator Ingestion + Alerts

**`orchestrator/ingestion.py`** — `Reading` Pydantic model gains:

```python
stuck: bool = False
```

`upload_readings` calls alert checking after writing to InfluxDB. For each reading:

```python
engine = AlertEngine(db)
for r in request.readings:
    if r.stuck:
        engine.check_stuck(
            agent_id, r.sensor_channel,
            r.location, r.plant_type, r.sensor_name
        )
    else:
        engine.resolve_stuck(agent_id, r.sensor_channel)
        engine.check_reading(
            agent_id, r.sensor_channel, r.moisture_percent,
            r.location, r.plant_type, r.sensor_name,
            thresholds=...  # see note below
        )
```

> **Note:** `check_reading()` requires threshold values. These must be looked up from the sensor config
> stored in the orchestrator. The mechanism for this lookup is left to the implementation plan.
> Wiring up `check_reading()` for `too_dry`/`too_wet` threshold alerts is a pre-existing gap that
> this feature will also fix as a byproduct.

**`orchestrator/alerts.py`** — two new methods on `AlertEngine`:

```python
def check_stuck(self, agent_id, sensor_channel, location, plant_type, sensor_name):
    """Create sensor_stuck alert if one doesn't already exist."""
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
            sensor_name=sensor_name
        )

def resolve_stuck(self, agent_id, sensor_channel):
    """Resolve sensor_stuck alert when sensor is moving again."""
    alert = self.db.query(ActiveAlert).filter(
        ActiveAlert.agent_id == agent_id,
        ActiveAlert.sensor_channel == sensor_channel,
        ActiveAlert.alert_type == "sensor_stuck",
        ActiveAlert.resolved_at.is_(None)
    ).first()
    if alert:
        self._resolve_alert(alert)
```

## Data Flow

```
SensorCollector.read()
  → appends raw_value to deque
  → if window full and range < min_range: reading.stuck = True + WARNING log
  → returns Reading(stuck=True/False, ...)

StorageManager.store_reading()
  → persists stuck flag to SQLite

SyncClient.sync_readings()
  → includes stuck in payload to orchestrator

orchestrator/ingestion.upload_readings()
  → writes to InfluxDB (includes stuck as tag/field)
  → calls AlertEngine.check_stuck() or resolve_stuck() + check_reading()

AlertEngine
  → creates/resolves sensor_stuck ActiveAlert in PostgreSQL
```

## Testing

- Unit tests for `calculate_moisture_percent` already exist; add tests for stuck detection logic in `test_collector.py`:
  - Window not yet full → `stuck=False`
  - Window full, range below threshold → `stuck=True`
  - Window full, range above threshold → `stuck=False`
  - `stuck_detection.enabled=False` → never flags
- Unit tests for `AlertEngine.check_stuck()` and `resolve_stuck()`
- Existing tests must continue to pass without changes to configs
