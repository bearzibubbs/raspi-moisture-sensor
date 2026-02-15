# Homepage Dashboard Integration

This guide shows how to integrate the moisture monitoring system with [gethomepage.dev](https://gethomepage.dev/).

## Overview

The API Server provides endpoints specifically designed for Homepage's `customapi` widget, displaying:
- Current moisture levels for all sensors
- Active alerts
- Fleet status
- Historical trends

## Prerequisites

1. API Server deployed and accessible
2. Homepage instance running
3. API endpoint URL (e.g., `https://api.example.com`)

## Configuration

### 1. Current Sensor Readings Widget

Shows all sensors with current moisture levels and alert status.

```yaml
- Current Moisture Levels:
    icon: mdi-water-percent
    widget:
      type: customapi
      url: https://api.example.com/api/v1/sensors/current
      method: GET
      mappings:
        - field: sensors
          label: Sensors
          format: list
          remap:
            - field: sensor_name
              label: Sensor
            - field: moisture_percent
              label: Moisture
              format: percent
            - field: alert_level
              label: Status
              format: text
```

### 2. Active Alerts Widget

Displays all active alerts across the fleet.

```yaml
- Moisture Alerts:
    icon: mdi-alert
    widget:
      type: customapi
      url: https://api.example.com/api/v1/alerts/active
      method: GET
      mappings:
        - field: alerts
          label: Active Alerts
          format: list
          remap:
            - field: sensor_name
              label: Sensor
            - field: alert_type
              label: Type
            - field: triggered_at
              label: Since
              format: relativeDate
```

### 3. Fleet Status Widget

Shows agent connectivity and health.

```yaml
- Fleet Status:
    icon: mdi-lan
    widget:
      type: customapi
      url: https://api.example.com/api/v1/fleet/status
      method: GET
      mappings:
        - field:
            agents_online: Online Agents
        - field:
            agents_offline: Offline Agents
        - field:
            total_sensors: Total Sensors
```

### 4. Sensor Detail Widget

Shows historical data for a specific sensor.

```yaml
- Greenhouse Tomato:
    icon: mdi-sprout
    widget:
      type: customapi
      url: https://api.example.com/api/v1/sensors/pi-greenhouse-01/0/timeseries?hours=24
      method: GET
      chart: true
      mappings:
        - field: timestamps
          label: Time
          format: datetime
        - field: moisture_values
          label: Moisture %
          format: number
```

## Complete Dashboard Example

```yaml
---
# homepage services.yaml
- Moisture Monitoring:
    icon: mdi-water
    description: Greenhouse moisture sensors
    href: https://api.example.com

- Current Readings:
    icon: mdi-water-percent
    widget:
      type: customapi
      url: https://api.example.com/api/v1/sensors/current
      refreshInterval: 60000  # 1 minute
      method: GET
      display: list

- Active Alerts:
    icon: mdi-alert
    widget:
      type: customapi
      url: https://api.example.com/api/v1/alerts/active
      refreshInterval: 30000  # 30 seconds
      method: GET
      display: list

- Fleet Health:
    icon: mdi-lan
    widget:
      type: customapi
      url: https://api.example.com/api/v1/fleet/status
      refreshInterval: 60000
      method: GET
      display: grid
```

## API Response Examples

### Current Sensors Response

```json
{
  "sensors": [
    {
      "agent_id": "pi-greenhouse-01",
      "sensor_channel": 0,
      "sensor_name": "tomato-01",
      "location": "greenhouse",
      "plant_type": "tomato",
      "moisture_percent": 65.5,
      "last_reading": "2026-02-15T10:30:00Z",
      "alert_level": "ok"
    },
    {
      "agent_id": "pi-greenhouse-01",
      "sensor_channel": 2,
      "sensor_name": "cucumber-01",
      "location": "greenhouse",
      "plant_type": "cucumber",
      "moisture_percent": 25.2,
      "last_reading": "2026-02-15T10:30:00Z",
      "alert_level": "dry"
    }
  ]
}
```

### Active Alerts Response

```json
{
  "alerts": [
    {
      "alert_id": 123,
      "agent_id": "pi-greenhouse-01",
      "sensor_channel": 2,
      "sensor_name": "cucumber-01",
      "location": "greenhouse",
      "plant_type": "cucumber",
      "alert_type": "too_dry",
      "moisture_percent": 25.2,
      "threshold": 30.0,
      "triggered_at": "2026-02-15T08:15:00Z",
      "duration_minutes": 135
    }
  ]
}
```

### Fleet Status Response

```json
{
  "agents_online": 3,
  "agents_offline": 1,
  "total_sensors": 8,
  "agents": [
    {
      "agent_id": "pi-greenhouse-01",
      "status": "online",
      "last_heartbeat": "2026-02-15T10:30:00Z",
      "sensor_count": 3,
      "uptime_hours": 168.5
    }
  ]
}
```

### Time Series Response

```json
{
  "agent_id": "pi-greenhouse-01",
  "sensor_channel": 0,
  "sensor_name": "tomato-01",
  "location": "greenhouse",
  "plant_type": "tomato",
  "timestamps": [
    "2026-02-14T10:00:00Z",
    "2026-02-14T11:00:00Z",
    "2026-02-14T12:00:00Z"
  ],
  "moisture_values": [65.5, 64.2, 63.8],
  "min_value": 63.8,
  "max_value": 65.5,
  "avg_value": 64.5
}
```

## Advanced Configuration

### Custom Refresh Intervals

Adjust based on your needs:
```yaml
refreshInterval: 60000   # Current readings - 1 minute
refreshInterval: 30000   # Alerts - 30 seconds
refreshInterval: 300000  # Fleet status - 5 minutes
```

### Custom Styling

Apply CSS classes for alert levels:
```yaml
mappings:
  - field: alert_level
    label: Status
    format: text
    colorMap:
      ok: green
      dry: red
      wet: blue
      offline: gray
```

### Authentication

If your API requires authentication:
```yaml
widget:
  type: customapi
  url: https://api.example.com/api/v1/sensors/current
  headers:
    Authorization: Bearer YOUR_API_TOKEN
```

## Troubleshooting

### Widget Not Displaying Data

1. Check API endpoint is accessible from Homepage container
2. Verify CORS is enabled on API Server
3. Check Homepage logs: `docker logs homepage`
4. Test endpoint manually: `curl https://api.example.com/api/v1/sensors/current`

### Slow Loading

1. Reduce refresh intervals
2. Check API Server performance
3. Consider caching in API Server
4. Use CDN if API is geographically distant

### Authentication Issues

1. Verify API token is valid
2. Check token expiration
3. Ensure headers are correctly formatted

## Next Steps

1. Configure Homepage with your endpoints
2. Customize widget appearance
3. Set up multiple dashboard pages (per location, per plant type)
4. Configure Homepage authentication
5. Set up HTTPS for secure access
