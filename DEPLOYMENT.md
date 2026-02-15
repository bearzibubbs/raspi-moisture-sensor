# Deployment Guide

Complete deployment guide for the moisture monitoring system.

## System Architecture

```
┌─────────────────────────────────────────────────────┐
│                 Raspberry Pi Agents                  │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐ │
│  │  Pi Agent   │  │  Pi Agent   │  │  Pi Agent   │ │
│  │ (Container) │  │ (Container) │  │ (Container) │ │
│  │  + Sensors  │  │  + Sensors  │  │  + Sensors  │ │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘ │
└─────────┼─────────────────┼─────────────────┼───────┘
          │                 │                 │
          │ HTTPS           │ HTTPS           │ HTTPS
          │                 │                 │
┌─────────▼─────────────────▼─────────────────▼───────┐
│           Kubernetes Infrastructure                  │
│  ┌────────────────────────────────────────────────┐ │
│  │         Orchestrator Service (2 replicas)      │ │
│  │  - Agent registration & management             │ │
│  │  - Data ingestion                              │ │
│  │  - Alert engine                                │ │
│  │  - Configuration management                    │ │
│  └────────┬──────────────────┬────────────────────┘ │
│           │                  │                       │
│  ┌────────▼────────┐  ┌──────▼──────┐              │
│  │   PostgreSQL    │  │  InfluxDB   │              │
│  │  (StatefulSet)  │  │(StatefulSet)│              │
│  └─────────────────┘  └──────┬──────┘              │
│                               │                      │
│  ┌────────────────────────────▼────────────────────┐│
│  │      API Server Service (2 replicas)            ││
│  │  - Homepage integration endpoints               ││
│  │  - Time-series queries                          ││
│  │  - Fleet status                                 ││
│  └──────────────────────┬──────────────────────────┘│
└────────────────────────┼────────────────────────────┘
                         │ HTTPS
                         │
┌────────────────────────▼────────────────────────────┐
│              Homepage Dashboard                      │
│  - Current readings                                  │
│  - Active alerts                                     │
│  - Historical trends                                 │
│  - Fleet status                                      │
└──────────────────────────────────────────────────────┘
```

## Prerequisites

### For Kubernetes Infrastructure

- Kubernetes cluster (1.24+)
- kubectl configured
- NGINX Ingress Controller
- cert-manager for TLS
- Storage provisioner for PersistentVolumes
- Docker registry (optional, for custom images)

### For Raspberry Pi Agents

- Raspberry Pi (3B+ or later recommended)
- Grove Base HAT
- Capacitive or resistive moisture sensors
- Docker or Podman installed
- I2C enabled

## Deployment Steps

### 1. Deploy Kubernetes Infrastructure

#### Generate Secrets

```bash
cd k8s

# Copy secrets template
cp secrets-example.yaml secrets.yaml

# Generate secure passwords
echo "PostgreSQL password: $(openssl rand -base64 32)"
echo "InfluxDB password: $(openssl rand -base64 32)"
echo "InfluxDB token: $(openssl rand -base64 64)"

# Edit secrets.yaml with generated values
vim secrets.yaml
```

#### Update Ingress Hostnames

Edit these files with your actual domain names:
- `orchestrator-deployment.yaml` - Update `orchestrator.example.com`
- `api-server-deployment.yaml` - Update `api.example.com`

#### Build Docker Images

```bash
# Build orchestrator
cd ../orchestrator
docker build -t your-registry/moisture-monitoring/orchestrator:latest .
docker push your-registry/moisture-monitoring/orchestrator:latest

# Build API server
cd ../api-server
docker build -t your-registry/moisture-monitoring/api-server:latest .
docker push your-registry/moisture-monitoring/api-server:latest
```

Update image references in deployment manifests if using a registry.

#### Deploy to Kubernetes

```bash
cd ../k8s

# Deploy all resources
kubectl apply -k .

# Wait for databases to be ready
kubectl wait --for=condition=ready pod -l app=postgresql -n moisture-monitoring --timeout=300s
kubectl wait --for=condition=ready pod -l app=influxdb -n moisture-monitoring --timeout=300s

# Verify deployment
kubectl get pods -n moisture-monitoring
kubectl get svc -n moisture-monitoring
kubectl get ingress -n moisture-monitoring
```

#### Verify Services

```bash
# Check orchestrator health
curl https://orchestrator.example.com/health

# Check API server health
curl https://api.example.com/health

# View logs
kubectl logs -f deployment/orchestrator -n moisture-monitoring
kubectl logs -f deployment/api-server -n moisture-monitoring
```

### 2. Deploy Pi Agents

#### Create Bootstrap Token

```bash
# Create a bootstrap token via orchestrator API
curl -X POST https://orchestrator.example.com/bootstrap-tokens \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "description": "Token for pi-greenhouse-01",
    "expires_hours": 24
  }'

# Save the returned token for agent setup
```

#### Deploy on Raspberry Pi

```bash
# On the Raspberry Pi
git clone git@github.com:bearzibubbs/raspi-moisture-sensor.git
cd raspi-moisture-sensor/pi-agent

# Enable I2C
sudo raspi-config nonint do_i2c 0
sudo usermod -aG i2c $USER
# Log out and back in

# Create configuration
cp config.example.yaml config.yaml
vim config.yaml  # Edit with your sensor configuration

# Create environment file
cp .env.example .env
cat > .env <<EOF
ORCHESTRATOR_URL=https://orchestrator.example.com
AGENT_TOKEN=
LOG_LEVEL=INFO
EOF

# Create data directory
mkdir -p data

# Start agent
docker-compose up -d

# View logs
docker-compose logs -f

# Check status
curl http://localhost:8080/health
```

#### Calibrate Sensors

```bash
# Read sensor in air
docker-compose exec pi-agent python -c "from collector import read_sensor; print('Air:', read_sensor(0))"

# Read sensor in water
docker-compose exec pi-agent python -c "from collector import read_sensor; print('Water:', read_sensor(0))"

# Update config.yaml with calibration values
vim config.yaml

# Restart agent
docker-compose restart pi-agent
```

### 3. Configure Homepage

#### Add API Widgets

Edit Homepage's `services.yaml`:

```yaml
- Moisture Monitoring:
    icon: mdi-water
    description: Greenhouse sensors

- Current Readings:
    icon: mdi-water-percent
    widget:
      type: customapi
      url: https://api.example.com/api/v1/sensors/current
      refreshInterval: 60000
      method: GET
      display: list

- Active Alerts:
    icon: mdi-alert
    widget:
      type: customapi
      url: https://api.example.com/api/v1/alerts/active
      refreshInterval: 30000
      method: GET
      display: list

- Fleet Status:
    icon: mdi-lan
    widget:
      type: customapi
      url: https://api.example.com/api/v1/fleet/status
      refreshInterval: 60000
      method: GET
      display: grid
```

See `docs/HOMEPAGE_INTEGRATION.md` for complete configuration examples.

## Verification

### Check Data Flow

```bash
# 1. Verify agent is collecting data
docker-compose exec pi-agent sqlite3 /data/agent.db \
  "SELECT COUNT(*) FROM readings WHERE synced=0"

# 2. Check orchestrator received data
kubectl logs deployment/orchestrator -n moisture-monitoring | grep "Received readings"

# 3. Query InfluxDB directly
kubectl exec -n moisture-monitoring influxdb-0 -- \
  influx query 'from(bucket:"sensor-data") |> range(start: -1h) |> limit(n:10)'

# 4. Test API server endpoint
curl https://api.example.com/api/v1/sensors/current

# 5. Verify Homepage displays data
# Open Homepage in browser and check widgets
```

### Monitor System Health

```bash
# Kubernetes health
kubectl get pods -n moisture-monitoring -w

# Pi agent health
docker-compose ps
curl http://localhost:8080/metrics

# Database sizes
kubectl exec -n moisture-monitoring postgresql-0 -- \
  psql -U moisture_user -d moisture_monitor -c \
  "SELECT pg_size_pretty(pg_database_size('moisture_monitor'))"

kubectl exec -n moisture-monitoring influxdb-0 -- \
  du -sh /var/lib/influxdb2
```

## Scaling

### Add More Pi Agents

Repeat Pi agent deployment steps on additional Raspberry Pis. Each agent:
- Auto-generates unique ID from MAC address
- Self-registers with orchestrator using bootstrap token
- Operates independently with local caching

### Scale Kubernetes Services

```bash
# Scale orchestrator
kubectl scale deployment orchestrator --replicas=3 -n moisture-monitoring

# Scale API server
kubectl scale deployment api-server --replicas=3 -n moisture-monitoring
```

### Database Scaling

For high loads:
- PostgreSQL: Consider replication or managed service (RDS, Cloud SQL)
- InfluxDB: Use InfluxDB Cloud or cluster deployment

## Maintenance

### Backup

#### Kubernetes Infrastructure

```bash
# PostgreSQL
kubectl exec -n moisture-monitoring postgresql-0 -- \
  pg_dump -U moisture_user moisture_monitor > backup-$(date +%Y%m%d).sql

# InfluxDB
kubectl exec -n moisture-monitoring influxdb-0 -- \
  influx backup /tmp/backup
kubectl cp moisture-monitoring/influxdb-0:/tmp/backup ./influxdb-backup-$(date +%Y%m%d)
```

#### Pi Agents

```bash
# Data directory
tar -czf pi-agent-backup-$(date +%Y%m%d).tar.gz data/

# Configuration
cp config.yaml config-backup-$(date +%Y%m%d).yaml
```

### Updates

#### Kubernetes Services

```bash
# Build new images
cd orchestrator && docker build -t your-registry/orchestrator:v1.1 .
cd ../api-server && docker build -t your-registry/api-server:v1.1 .

# Push to registry
docker push your-registry/orchestrator:v1.1
docker push your-registry/api-server:v1.1

# Update deployments
kubectl set image deployment/orchestrator orchestrator=your-registry/orchestrator:v1.1 -n moisture-monitoring
kubectl set image deployment/api-server api-server=your-registry/api-server:v1.1 -n moisture-monitoring

# Watch rollout
kubectl rollout status deployment/orchestrator -n moisture-monitoring
kubectl rollout status deployment/api-server -n moisture-monitoring
```

#### Pi Agents

```bash
# Pull latest code
cd raspi-moisture-sensor/pi-agent
git pull

# Rebuild and restart
docker-compose up -d --build

# Verify
docker-compose logs -f pi-agent
curl http://localhost:8080/health
```

### Monitoring

Set up Prometheus + Grafana:

```bash
# Add ServiceMonitor resources for orchestrator and API server
kubectl apply -f monitoring/service-monitors.yaml

# Create dashboards for:
# - Agent health and connectivity
# - Sensor reading rates
# - Database sizes
# - Alert trends
# - API response times
```

## Troubleshooting

### Agent Not Connecting

1. Check network connectivity from Pi to orchestrator
2. Verify bootstrap token is valid and not expired
3. Review agent logs: `docker-compose logs pi-agent`
4. Test orchestrator endpoint: `curl https://orchestrator.example.com/health`

### Data Not Appearing in Homepage

1. Verify API server is running: `kubectl get pods -n moisture-monitoring`
2. Test API endpoint: `curl https://api.example.com/api/v1/sensors/current`
3. Check Homepage logs for errors
4. Verify CORS is configured correctly

### Sensors Reading Incorrectly

1. Recalibrate sensors (see calibration steps above)
2. Verify sensor type in config.yaml (capacitive vs resistive)
3. Check physical connections to Grove HAT
4. Test hardware: `sudo i2cdetect -y 1`

### Database Storage Issues

1. Check PVC sizes: `kubectl get pvc -n moisture-monitoring`
2. Expand volumes if needed
3. Verify cleanup jobs are running
4. Consider data retention policies

## Security Checklist

- [ ] Strong passwords generated for PostgreSQL and InfluxDB
- [ ] secrets.yaml not committed to git
- [ ] TLS enabled for all external endpoints
- [ ] cert-manager configured for automatic certificate rotation
- [ ] Bootstrap tokens expire after 24 hours
- [ ] Agent tokens rotated periodically
- [ ] Network policies configured to restrict pod-to-pod traffic
- [ ] RBAC enabled with minimal permissions
- [ ] Kubernetes secrets encrypted at rest
- [ ] Regular security updates applied

## Cost Optimization

- Use node affinity to schedule workloads on cheaper nodes
- Set resource requests/limits appropriately
- Enable horizontal pod autoscaling for orchestrator and API server
- Use storage classes with appropriate performance tiers
- Consider spot/preemptible instances for non-critical workloads
- Implement InfluxDB data retention policies

## Next Steps

1. Configure alerting (email, Slack, etc.)
2. Set up Grafana dashboards for detailed monitoring
3. Implement data retention policies
4. Add authentication to Homepage
5. Create backup automation
6. Document runbooks for common issues
7. Set up CI/CD pipeline for updates
8. Configure log aggregation (ELK, Loki)
9. Implement advanced alert rules (e.g., trend analysis)
10. Add mobile notifications for critical alerts
