# Agent-Based Moisture Monitoring System Design

**Date:** 2026-02-15
**Status:** Approved
**Architecture:** Agent-based with central orchestration

## Overview

Transform the existing Raspberry Pi moisture sensor testing setup into a production monitoring system with:
- Autonomous Pi agents that collect sensor data every minute
- Local SQLite caching for resilience during network outages
- Central orchestrator service in Kubernetes for fleet management
- InfluxDB time-series storage for sensor readings
- Homepage dashboard integration for visualization and alerts

## System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                         Kubernetes                          │
│                                                             │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────────┐  │
│  │Orchestrator │←→│  InfluxDB    │←→│   API Server    │  │
│  │   Service   │  │              │  │                 │  │
│  └──────┬──────┘  └──────────────┘  └────────┬────────┘  │
│         │                                      │           │
└─────────┼──────────────────────────────────────┼───────────┘
          │                                      │
          ├─── Agent Registration               │
          ├─── Heartbeats                       │
          ├─── Config Pull                      │
          │                                      │
          │                              ┌───────▼────────┐
          │                              │   Homepage     │
          │                              │   Dashboard    │
          │                              └────────────────┘
          │
    ┌─────▼──────┐      ┌──────────┐       ┌──────────┐
    │ Pi Agent 1 │      │Pi Agent 2│  ...  │Pi Agent N│
    │            │      │          │       │          │
    │ ┌────────┐ │      │┌────────┐│       │┌────────┐│
    │ │SQLite  │ │      ││SQLite  ││       ││SQLite  ││
    │ │Cache   │ │      ││Cache   ││       ││Cache   ││
    │ └────────┘ │      │└────────┘│       │└────────┘│
    │            │      │          │       │          │
    │ Sensors:   │      │Sensors:  │       │Sensors:  │
    │ A0, A2, A4 │      │A0, A2    │       │A0, A2, A4│
    └────────────┘      └──────────┘       └──────────┘
```

### Data Flow

1. Pi Agents read sensors every 1 minute
2. Readings stored locally in SQLite (resilience)
3. Agent sends readings to Orchestrator via HTTP POST
4. Orchestrator validates and writes to InfluxDB
5. Orchestrator serves config updates via pull model
6. API Server queries InfluxDB and serves Homepage
7. Homepage displays current readings, trends, and alerts

### Key Design Principles

- **Autonomous agents**: Pis work independently, even offline
- **Self-registration**: Agents announce themselves to orchestrator on startup
- **Eventual consistency**: Data syncs when network is available
- **Centralized intelligence**: Orchestrator handles fleet coordination
- **Pull-based config**: Agents pull configuration from orchestrator

## Component Details

### 1. Pi Agent

**Responsibilities:**
- Read moisture sensors every 1 minute
- Store readings in local SQLite database
- Send data to orchestrator when online
- Pull config updates from orchestrator
- Self-register with orchestrator on startup
- Report health metrics (CPU, memory, disk, temperature)
- Expose local REST API for management

**Technology Stack:**
- Python 3.11+
- FastAPI (lightweight, async)
- SQLite3
- APScheduler (for 1-minute cron jobs)
- httpx (async requests to orchestrator)
- grove.py (sensor library)

**SQLite Schema:**
```sql
CREATE TABLE readings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp INTEGER NOT NULL,        -- Unix timestamp
    sensor_channel INTEGER NOT NULL,   -- 0, 2, 4
    sensor_type TEXT NOT NULL,         -- 'resistive' or 'capacitive'
    raw_value INTEGER NOT NULL,
    moisture_percent REAL NOT NULL,
    location TEXT,                     -- e.g., 'greenhouse'
    plant_type TEXT,                   -- e.g., 'tomato'
    sensor_name TEXT,                  -- e.g., 'sensor-01'
    synced BOOLEAN DEFAULT 0,          -- 0=not synced, 1=synced
    created_at INTEGER DEFAULT (strftime('%s','now'))
);

CREATE INDEX idx_timestamp ON readings(timestamp);
CREATE INDEX idx_synced ON readings(synced);
CREATE INDEX idx_sensor ON readings(sensor_channel);

CREATE TABLE agent_metadata (
    key TEXT PRIMARY KEY,
    value TEXT
);
-- Stores: agent_id, last_sync, orchestrator_url, api_token
```

**Config File Format (config.yaml):**
```yaml
agent:
  id: "pi-a3f2b1c4"  # Generated once, permanent
  orchestrator_url: "https://orchestrator.example.com"
  bootstrap_token: "${BOOTSTRAP_TOKEN}"  # For first registration
  agent_token: "${AGENT_TOKEN}"  # Permanent token (auto-populated)
  sync_interval_seconds: 60
  config_pull_interval_seconds: 300  # Check for config updates every 5 min

sensors:
  - channel: 0
    type: "capacitive"
    calibration:
      min: 300  # wet
      max: 800  # dry
    labels:
      location: "greenhouse"
      plant_type: "tomato"
      sensor_name: "tomato-01"
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
      location: "greenhouse"
      plant_type: "basil"
      sensor_name: "basil-01"
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

**Local API Endpoints:**
```
GET  /health              # System health + agent status
GET  /config              # Current configuration
PUT  /config              # Update configuration
GET  /sensors             # List configured sensors
GET  /sensors/{channel}   # Get specific sensor info
POST /sensors/{channel}/test  # Trigger immediate reading
GET  /readings/recent     # Last 100 readings
GET  /storage/stats       # Database size, sync status
```

**Storage Calculation (1 week offline):**
- 3 sensors × 1 reading/min × 10,080 min = 30,240 readings
- ~200 bytes per reading = 6 MB per week
- With overhead: ~170 MB total for 1 week
- 32GB SD card can cache ~165 weeks (~3 years) of data

### 2. Orchestrator

**Responsibilities:**
- Accept agent registrations and issue permanent tokens
- Receive sensor readings from agents and write to InfluxDB
- Maintain agent registry (list of known agents, last heartbeat)
- Serve config updates to agents (pull model)
- Calculate alert status across all sensors
- Provide fleet-wide status and metrics
- Handle agent authentication

**Technology Stack:**
- Python 3.11+
- FastAPI
- PostgreSQL (for agent registry, config, alert rules)
- Optional Redis for async tasks
- influxdb-client-python

**PostgreSQL Schema:**
```sql
CREATE TABLE agents (
    agent_id TEXT PRIMARY KEY,
    hostname TEXT,
    hardware TEXT,
    agent_token_hash TEXT NOT NULL,
    registered_at TIMESTAMP DEFAULT NOW(),
    last_heartbeat TIMESTAMP,
    last_sync_at TIMESTAMP,
    status TEXT DEFAULT 'active',
    desired_config_version INTEGER DEFAULT 1,
    applied_config_version INTEGER DEFAULT 0,
    metadata JSONB
);

CREATE TABLE bootstrap_tokens (
    token_hash TEXT PRIMARY KEY,
    created_at TIMESTAMP DEFAULT NOW(),
    expires_at TIMESTAMP NOT NULL,  -- 24 hours from creation
    used_count INTEGER DEFAULT 0,
    max_uses INTEGER DEFAULT NULL
);

CREATE TABLE alert_rules (
    id SERIAL PRIMARY KEY,
    agent_id TEXT REFERENCES agents(agent_id),
    sensor_channel INTEGER,
    dry_threshold REAL,
    wet_threshold REAL,
    enabled BOOLEAN DEFAULT TRUE
);

CREATE TABLE active_alerts (
    id SERIAL PRIMARY KEY,
    agent_id TEXT REFERENCES agents(agent_id),
    sensor_channel INTEGER,
    alert_type TEXT,
    triggered_at TIMESTAMP DEFAULT NOW(),
    resolved_at TIMESTAMP,
    acknowledged BOOLEAN DEFAULT FALSE,
    moisture_percent REAL,
    threshold REAL,
    location TEXT,
    plant_type TEXT,
    sensor_name TEXT
);
```

**API Endpoints:**

Agent Communication:
```
POST /agents/register              # Register new agent (bootstrap token)
POST /agents/{agent_id}/heartbeat  # Periodic heartbeat
POST /agents/{agent_id}/readings   # Upload sensor readings (batch)
GET  /agents/{agent_id}/config     # Pull latest config
POST /agents/{agent_id}/health     # Report health metrics
```

Admin/Management:
```
GET  /agents                       # List all agents
GET  /agents/{agent_id}            # Get agent details
PUT  /agents/{agent_id}/config     # Update agent config
DELETE /agents/{agent_id}          # Decommission agent

POST /bootstrap-tokens             # Generate new bootstrap token
GET  /bootstrap-tokens             # List active tokens
DELETE /bootstrap-tokens/{token}   # Revoke token

GET  /alerts                       # List active alerts
GET  /alerts/history               # Alert history
POST /alerts/{alert_id}/acknowledge # Acknowledge alert
```

Query/Data Access:
```
GET  /data/current                 # Current readings for all sensors
GET  /data/sensor/{location}/{plant}/{sensor}  # Specific sensor data
GET  /data/timeseries              # Query historical data from InfluxDB
GET  /fleet/status                 # Overall fleet health
```

**InfluxDB Data Model:**
```
Measurement: moisture_reading

Tags (indexed):
  - agent_id        (e.g., "pi-a3f2b1c4") [permanent]
  - sensor_channel  (e.g., "0", "2", "4") [permanent]
  - sensor_type     (e.g., "capacitive", "resistive")
  - location        (e.g., "greenhouse") [flexible]
  - plant_type      (e.g., "tomato") [flexible]
  - sensor_name     (e.g., "tomato-01") [flexible]

Fields:
  - raw_value        (integer)
  - moisture_percent (float)

Timestamp: Reading timestamp from agent
```

### 3. API Server

**Responsibilities:**
- Query InfluxDB for sensor data
- Serve current readings and time-series data for Homepage
- Calculate aggregate metrics (averages, min/max)
- Format alert information for display
- Provide REST API for Homepage widgets

**Technology Stack:**
- Python 3.11+
- FastAPI
- influxdb-client-python
- Optional Redis for caching

**API Endpoints:**
```
GET /api/v1/sensors/current
GET /api/v1/sensors/{agent_id}/{channel}/timeseries?hours=24
GET /api/v1/alerts/active
GET /api/v1/fleet/status
```

**Performance Optimizations:**
- Cache `/sensors/current` for 30 seconds
- Downsample time-series queries (1-min → 5-min averages for 7-day views)
- Use InfluxDB aggregation functions
- Query timeout: 10 seconds

### 4. Homepage Integration

**Approach:** Use Homepage's built-in `customapi` widget

**Configuration (services.yaml):**
```yaml
- Moisture Monitoring:
    icon: mdi-sprout
    description: Plant moisture sensors

    - Current Readings:
        icon: mdi-water-percent
        widget:
          type: customapi
          url: https://api-server.example.com/api/v1/sensors/current
          method: GET
          headers:
            Authorization: Bearer {{HOMEPAGE_API_TOKEN}}
          refreshInterval: 60000

    - Active Alerts:
        icon: mdi-alert
        widget:
          type: customapi
          url: https://api-server.example.com/api/v1/alerts/active
          method: GET
          headers:
            Authorization: Bearer {{HOMEPAGE_API_TOKEN}}
          refreshInterval: 30000

    - Fleet Status:
        icon: mdi-server-network
        widget:
          type: customapi
          url: https://api-server.example.com/api/v1/fleet/status
          method: GET
          headers:
            Authorization: Bearer {{HOMEPAGE_API_TOKEN}}
          refreshInterval: 60000
```

## Security & Authentication

### Token Strategy

**Bootstrap Token:**
- Shared secret for initial agent registration
- Expires in 24 hours
- Can be revoked or limited to max uses
- Admin generates via orchestrator CLI

**Agent Token:**
- Unique permanent token per agent
- Issued by orchestrator during first registration
- Stored in agent's SQLite database
- Used for all ongoing agent-orchestrator communication
- Can be revoked/regenerated if compromised

**Local API Token:**
- Auto-generated on agent first start
- Used to manage Pi's local API
- Stored in agent environment variables

### Registration Flow

```
1. Pi Setup
   └─> Set BOOTSTRAP_TOKEN, ORCHESTRATOR_URL

2. First Startup
   └─> Agent → POST /agents/register (with bootstrap token)

3. Orchestrator validates bootstrap token
   └─> Generates unique agent_token
   └─> Returns agent_token + config

4. Agent stores permanent token
   └─> Uses for all future communication
```

## Agent Identity vs. Data Labels

### Agent ID (Permanent)
- Generated once during setup (MAC address hash or UUID)
- Tied to physical Pi hardware
- Never changes
- Used for authentication and tracking

### Data Labels (Flexible)
- Defined in agent config
- Can change anytime (location, plant_type, sensor_name)
- Used for organizing and querying data
- Allows sensors to be moved/repurposed

**Example:** Agent ID stays "pi-a3f2b1c4" forever, but labels can change from "greenhouse/tomato" to "indoor/basil" when sensor is moved.

## Alert System

### Alert Types
- `too_dry`: moisture_percent < dry_threshold
- `too_wet`: moisture_percent > wet_threshold
- `sensor_offline`: No reading for > 10 minutes
- `agent_offline`: No heartbeat for > 5 minutes

### Alert States
```
Normal → Triggered → Acknowledged → Resolved
```

### Hysteresis
- Alert triggers at threshold (e.g., 30%)
- Alert resolves at threshold + hysteresis (e.g., 35%)
- Prevents alert flapping at boundary

### Alert Severity
- **Warning**: 10-20% outside threshold range
- **Critical**: > 20% outside threshold, or offline

### Alert Calculation
- Orchestrator evaluates thresholds when receiving readings
- Centralized logic (no threshold checking on agents)
- Auto-resolves when readings return to normal range

## Error Handling & Resilience

### Agent Resilience

**Network Failures:**
- Continue reading sensors offline
- Store readings in SQLite with `synced=0`
- Retry sync every 60s with exponential backoff
- Batch upload on reconnection

**Sensor Reading Failures:**
- Retry 3 times with 1s delay
- Log error but don't crash
- Store NULL in DB
- Orchestrator creates `sensor_offline` alert

**SQLite Corruption:**
- Integrity check on startup
- Auto-backup before VACUUM
- Recovery mode: rebuild from sync state

**Configuration Errors:**
- Validate config on load (Pydantic)
- Fall back to last known good config
- Report error to orchestrator

### Orchestrator Resilience

**InfluxDB Unavailable:**
- Buffer readings in PostgreSQL
- Background task retries periodically

**PostgreSQL Unavailable:**
- Return 503 Service Unavailable
- Agents retry with exponential backoff

**Duplicate Data:**
- Deduplicate readings by (agent_id, timestamp, channel)
- Prevents double-counting on retry

### API Server Resilience

**InfluxDB Query Failures:**
- Return cached data with stale indicator
- Cache last successful response for 5 minutes

**Slow Queries:**
- Query timeout: 10 seconds
- Downsample data for long time ranges

### Health Monitoring

**Agent Health:**
- Exposes `/health` endpoint with:
  - Sensor status
  - Storage stats (DB size, unsynced count)
  - Orchestrator connectivity
  - System metrics (CPU, memory, disk, temperature)

**Orchestrator Health:**
- Exposes `/health` endpoint with:
  - Component status (Postgres, InfluxDB, Redis)
  - Agent counts (total, online, offline)
  - Recent activity stats

**Kubernetes:**
- Liveness/readiness probes on `/health`
- Auto-restart on failure
- Graceful shutdown handling (SIGTERM)

### Automatic Recovery
- Agent: systemd service with Restart=always
- Orchestrator: Kubernetes deployment with replicas=2
- Database connection pooling with auto-reconnect
- Log rotation to prevent disk filling

## Deployment

### Pi Agent Installation

**Setup Script (install-agent.sh):**
```bash
#!/bin/bash
set -e

# Install dependencies
sudo ./raspi-gpio-setup.sh

# Generate permanent agent ID
if [ ! -f /opt/pi-agent/.agent_id ]; then
    AGENT_ID="pi-$(cat /sys/class/net/eth0/address | sha256sum | cut -c1-12)"
    echo "$AGENT_ID" | sudo tee /opt/pi-agent/.agent_id
else
    AGENT_ID=$(cat /opt/pi-agent/.agent_id)
fi

# Create directories
sudo mkdir -p /opt/pi-agent
sudo mkdir -p /var/lib/pi-agent
sudo mkdir -p /var/log/pi-agent

# Copy agent files
sudo cp -r pi-agent/* /opt/pi-agent/
cd /opt/pi-agent
sudo pip3 install -r requirements.txt

# Generate local API token
if [ -z "$LOCAL_API_TOKEN" ]; then
    LOCAL_API_TOKEN=$(openssl rand -hex 32)
fi

# Create environment file
sudo tee /opt/pi-agent/.env > /dev/null <<EOF
AGENT_ID=$AGENT_ID
ORCHESTRATOR_URL=${ORCHESTRATOR_URL}
BOOTSTRAP_TOKEN=${BOOTSTRAP_TOKEN}
LOCAL_API_TOKEN=${LOCAL_API_TOKEN}
EOF

# Create systemd service
sudo tee /etc/systemd/system/pi-agent.service > /dev/null <<EOF
[Unit]
Description=Moisture Sensor Agent
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/opt/pi-agent
EnvironmentFile=/opt/pi-agent/.env
ExecStart=/usr/bin/python3 /opt/pi-agent/agent.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# Enable and start
sudo systemctl daemon-reload
sudo systemctl enable pi-agent
sudo systemctl start pi-agent

echo "✓ Agent ID: $AGENT_ID (permanent)"
echo "⚠ NEXT: Edit /opt/pi-agent/config.yaml to set sensor labels"
```

### Kubernetes Deployment

**Namespace:**
```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: moisture-monitoring
```

**Orchestrator:**
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orchestrator
  namespace: moisture-monitoring
spec:
  replicas: 2
  selector:
    matchLabels:
      app: orchestrator
  template:
    metadata:
      labels:
        app: orchestrator
    spec:
      containers:
      - name: orchestrator
        image: orchestrator:v1.0.0
        ports:
        - containerPort: 8000
        env:
        - name: POSTGRES_URL
          valueFrom:
            secretKeyRef:
              name: db-credentials
              key: postgres-url
        - name: INFLUXDB_URL
          valueFrom:
            secretKeyRef:
              name: db-credentials
              key: influxdb-url
        - name: INFLUXDB_TOKEN
          valueFrom:
            secretKeyRef:
              name: db-credentials
              key: influxdb-token
        resources:
          requests:
            memory: "256Mi"
            cpu: "250m"
          limits:
            memory: "512Mi"
            cpu: "500m"
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 10
          periodSeconds: 30
        readinessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 5
          periodSeconds: 10
```

**Databases:**
```bash
# InfluxDB
helm repo add influxdata https://helm.influxdata.com/
helm install influxdb influxdata/influxdb2 \
  --namespace moisture-monitoring \
  --set persistence.size=20Gi

# PostgreSQL
helm repo add bitnami https://charts.bitnami.com/bitnami
helm install postgresql bitnami/postgresql \
  --namespace moisture-monitoring \
  --set primary.persistence.size=10Gi
```

## Operations

### Monitoring
- Prometheus metrics from all services
- Grafana dashboards for system health
- Alert on agent offline > 10 minutes
- Alert on orchestrator errors

### Backup Strategy
- InfluxDB: Daily snapshots, retain 30 days
- PostgreSQL: Daily backups, retain 7 days
- Agent configs: Version controlled in git

### Log Aggregation
- Agent logs: Journald, optionally forwarded to orchestrator
- K8s logs: Loki or ELK stack

## Testing Strategy

### Unit Tests
- Agent: Sensor reading, config validation, storage operations
- Orchestrator: Registration, authentication, alert logic
- API Server: Query formatting, data transformation

### Integration Tests
- Agent ↔ Orchestrator: Registration and sync flow
- Offline resilience: Agent caches and syncs after reconnection
- Config pull: Agent detects and applies config updates

### End-to-End Tests
- Sensor reading flows to Homepage display
- Alert triggers and appears in Homepage
- Multi-Pi scenario with different sensor configurations

### Performance Tests
- Agent: CPU < 5%, Memory < 50 MB
- Orchestrator: Handle 100 agents × 3 sensors (180 readings/min)
- API Server: Current readings < 500ms, Time-series < 2s
- InfluxDB: Write latency < 100ms

## Future Enhancements

- Grafana dashboards for detailed time-series visualization
- Push notifications via Pushover/ntfy
- Automated watering control based on thresholds
- Machine learning for predictive watering schedules
- Mobile app for remote monitoring
- Multi-tenant support for community gardens

## Success Criteria

- [ ] Agents operate autonomously for 1 week offline
- [ ] Zero data loss during network outages
- [ ] Alerts visible in Homepage within 2 minutes of trigger
- [ ] Config updates applied within 5 minutes
- [ ] System handles 10+ Pis with 30+ sensors
- [ ] Query performance < 2 seconds for 7-day data
- [ ] Agent resource usage minimal (< 5% CPU)
