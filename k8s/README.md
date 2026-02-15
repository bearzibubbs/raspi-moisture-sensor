# Kubernetes Deployment

This directory contains Kubernetes manifests for deploying the moisture monitoring infrastructure.

## Architecture

- **PostgreSQL**: Agent registry, alert tracking, configuration management
- **InfluxDB**: Time-series sensor data storage
- **Orchestrator**: Agent management, data ingestion, alert engine
- **API Server**: Homepage integration endpoints

## Prerequisites

1. Kubernetes cluster (1.24+)
2. kubectl configured
3. NGINX Ingress Controller
4. cert-manager (for TLS certificates)
5. Storage provisioner for PersistentVolumes

## Deployment Steps

### 1. Create Secrets

Copy the example secrets file and fill in actual values:

```bash
cp secrets-example.yaml secrets.yaml
# Edit secrets.yaml with actual passwords and tokens
```

**Generate secure passwords:**
```bash
# PostgreSQL password
openssl rand -base64 32

# InfluxDB password
openssl rand -base64 32

# InfluxDB admin token
openssl rand -base64 64
```

### 2. Update Ingress Hostnames

Edit the following files to use your actual domain names:
- `orchestrator-deployment.yaml` - Change `orchestrator.example.com`
- `api-server-deployment.yaml` - Change `api.example.com`

### 3. Deploy with Kustomize

Uncomment the `secrets.yaml` line in `kustomization.yaml`, then:

```bash
kubectl apply -k .
```

Or deploy manually:

```bash
kubectl apply -f namespace.yaml
kubectl apply -f secrets.yaml
kubectl apply -f postgresql-statefulset.yaml
kubectl apply -f influxdb-statefulset.yaml

# Wait for databases to be ready
kubectl wait --for=condition=ready pod -l app=postgresql -n moisture-monitoring --timeout=300s
kubectl wait --for=condition=ready pod -l app=influxdb -n moisture-monitoring --timeout=300s

kubectl apply -f orchestrator-deployment.yaml
kubectl apply -f api-server-deployment.yaml
```

### 4. Verify Deployment

```bash
# Check all pods are running
kubectl get pods -n moisture-monitoring

# Check services
kubectl get svc -n moisture-monitoring

# Check ingress
kubectl get ingress -n moisture-monitoring

# View logs
kubectl logs -f deployment/orchestrator -n moisture-monitoring
kubectl logs -f deployment/api-server -n moisture-monitoring
```

## Building Docker Images

### Orchestrator

```bash
cd orchestrator
docker build -t moisture-monitoring/orchestrator:latest .
```

### API Server

```bash
cd api-server
docker build -t moisture-monitoring/api-server:latest .
```

If using a registry:
```bash
docker tag moisture-monitoring/orchestrator:latest your-registry/orchestrator:latest
docker tag moisture-monitoring/api-server:latest your-registry/api-server:latest
docker push your-registry/orchestrator:latest
docker push your-registry/api-server:latest
```

Update image names in deployment manifests accordingly.

## Configuration

### Orchestrator Configuration

Environment variables in `orchestrator-deployment.yaml`:
- `DATABASE_URL`: PostgreSQL connection string
- `INFLUXDB_URL`: InfluxDB endpoint
- `INFLUXDB_TOKEN`: InfluxDB admin token
- `INFLUXDB_ORG`: Organization name
- `INFLUXDB_BUCKET`: Bucket name
- `LOG_LEVEL`: Logging level (DEBUG, INFO, WARNING, ERROR)
- `ALERT_CHECK_INTERVAL`: Alert check frequency in seconds

### API Server Configuration

Environment variables in `api-server-deployment.yaml`:
- `INFLUXDB_URL`: InfluxDB endpoint
- `INFLUXDB_TOKEN`: InfluxDB admin token
- `INFLUXDB_ORG`: Organization name
- `INFLUXDB_BUCKET`: Bucket name
- `LOG_LEVEL`: Logging level

## Scaling

Scale replicas as needed:

```bash
kubectl scale deployment orchestrator --replicas=3 -n moisture-monitoring
kubectl scale deployment api-server --replicas=3 -n moisture-monitoring
```

## Database Management

### PostgreSQL Backup

```bash
kubectl exec -n moisture-monitoring postgresql-0 -- pg_dump -U moisture_user moisture_monitor > backup.sql
```

### InfluxDB Backup

```bash
kubectl exec -n moisture-monitoring influxdb-0 -- influx backup /tmp/backup
kubectl cp moisture-monitoring/influxdb-0:/tmp/backup ./influxdb-backup
```

## Troubleshooting

### Check Database Connectivity

```bash
# PostgreSQL
kubectl exec -it postgresql-0 -n moisture-monitoring -- psql -U moisture_user -d moisture_monitor

# InfluxDB
kubectl exec -it influxdb-0 -n moisture-monitoring -- influx ping
```

### View All Resources

```bash
kubectl get all -n moisture-monitoring
```

### Delete Everything

```bash
kubectl delete -k .
# Or
kubectl delete namespace moisture-monitoring
```

## Security Notes

1. **Never commit secrets.yaml** - Add to .gitignore
2. Use strong, randomly generated passwords
3. Rotate tokens regularly
4. Configure network policies to restrict pod-to-pod communication
5. Enable RBAC and limit service account permissions
6. Use TLS for all external endpoints (handled by ingress)
7. Consider using a secrets management solution (Sealed Secrets, External Secrets Operator, Vault)

## Monitoring

Add Prometheus ServiceMonitor resources to enable metrics collection:

```yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: orchestrator
  namespace: moisture-monitoring
spec:
  selector:
    matchLabels:
      app: orchestrator
  endpoints:
  - port: http
    path: /metrics
```
