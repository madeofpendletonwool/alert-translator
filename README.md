# Alert Translator

A lightweight Flask middleware service that translates Kubernetes alerts from Prometheus/Alertmanager into beautifully formatted notifications for NTFY servers. Perfect for getting clean, emoji-rich alerts on your mobile device or desktop.

## Features

- 🚀 **Multi-Server Support**: Send alerts to multiple NTFY servers simultaneously
- 🎨 **Rich Formatting**: Clean, emoji-enhanced notifications with proper severity levels
- 🏷️ **Smart Labeling**: Automatically extracts and formats Kubernetes labels (namespace, pod, instance, job)
- ⚡ **Multiple Severity Levels**: Critical, Warning, and Info alerts with appropriate priorities
- 🔄 **Resolution Tracking**: Handles both firing and resolved alert states
- 📊 **Health Monitoring**: Built-in health check and test endpoints
- 🛡️ **Error Handling**: Robust error handling with detailed logging
- 🐳 **Container Ready**: Lightweight Alpine-based Docker container

## Quick Start

### Docker Run

```bash
docker run -d \
  --name alert-translator \
  -p 5000:5000 \
  -e NTFY_URLS='["http://ntfy.ntfy.svc.cluster.local", "https://ntfy.server.com"]' \
  -e NTFY_TOPIC="k8s-alerts" \
  your-registry/alert-translator:latest
```

### Kubernetes Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: alert-translator
  namespace: monitoring
spec:
  replicas: 2
  selector:
    matchLabels:
      app: alert-translator
  template:
    metadata:
      labels:
        app: alert-translator
    spec:
      containers:
      - name: alert-translator
        image: your-registry/alert-translator:latest
        ports:
        - containerPort: 5000
        env:
        - name: NTFY_URLS
          value: '["http://ntfy.ntfy.svc.cluster.local", "https://ntfy.server.com"]'
        - name: NTFY_TOPIC
          value: "kubernetes-alerts"
        livenessProbe:
          httpGet:
            path: /health
            port: 5000
          initialDelaySeconds: 10
          periodSeconds: 30
        readinessProbe:
          httpGet:
            path: /health
            port: 5000
          initialDelaySeconds: 5
          periodSeconds: 10
---
apiVersion: v1
kind: Service
metadata:
  name: alert-translator
  namespace: monitoring
spec:
  selector:
    app: alert-translator
  ports:
  - port: 80
    targetPort: 5000
  type: ClusterIP
```

## Configuration

### Environment Variables

| Variable | Description | Default | Example |
|----------|-------------|---------|---------|
| `NTFY_URLS` | NTFY server URLs (JSON array or comma-separated) | `http://ntfy.ntfy.svc.cluster.local` | `["http://server1", "http://server2"]` |
| `NTFY_URL` | Legacy single URL support | `http://ntfy.ntfy.svc.cluster.local` | `http://ntfy.example.com` |
| `NTFY_TOPIC` | NTFY topic name | `kubernetes-alerts` | `my-alerts` |

### NTFY_URLS Format Options

**JSON Array (Recommended):**
```bash
NTFY_URLS='["http://ntfy.ntfy.svc.cluster.local", "https://ntfy.server.com"]'
```

**Comma-Separated:**
```bash
NTFY_URLS="http://ntfy.ntfy.svc.cluster.local,https://ntfy.server.com"
```

**Single URL (Legacy):**
```bash
NTFY_URL="http://ntfy.ntfy.svc.cluster.local"
```

## Alertmanager Configuration

Configure Alertmanager to send webhooks to the alert-translator:

```yaml
global:
  # ... other config

route:
  # ... your routing rules

receivers:
- name: 'ntfy-alerts'
  webhook_configs:
  - url: 'http://alert-translator.monitoring.svc.cluster.local/webhook'
    send_resolved: true
    http_config:
      timeout: 10s
```

## API Endpoints

### POST /webhook
**Primary endpoint for receiving Alertmanager webhooks**

Expected payload: Standard Alertmanager webhook format

Response:
```json
{
  "status": "success",
  "alerts_processed": 2,
  "notifications_sent": 4,
  "servers_configured": 2
}
```

### GET /health
**Health check endpoint**

Response:
```json
{
  "status": "healthy",
  "servers_configured": 2,
  "ntfy_servers": ["http://server1", "http://server2"],
  "topic": "kubernetes-alerts"
}
```

### POST /test
**Send a test notification to all configured servers**

Response:
```json
{
  "status": "success",
  "message": "Test notification sent",
  "sent_to_servers": 2,
  "total_servers": 2
}
```

## Alert Severity Levels

| Severity | Priority | Tags | Prefix |
|----------|----------|------|--------|
| Critical | urgent | critical, skull | CRITICAL |
| Warning | high | warning | WARNING |
| Info | default | info | INFO |

## Notification Format

### Alert Structure
```
🔥 Status: FIRING
📝 Summary: High CPU usage detected
📋 Description: CPU usage is above 90% for 5 minutes
🏷️ Labels:
📍 Namespace: production
📦 Pod: web-app-12345
🖥️ Instance: worker-node-1
⚙️ Job: kubernetes-pods
⏱️ Duration: 5 minutes
⏰ Started: 2025-05-23T10:30:00Z
📚 Runbook: https://runbook.example.com/cpu-alerts
```

### Resolved Alerts
```
✅ Status: RESOLVED
📝 Summary: High CPU usage resolved
...
✅ Resolved: 2025-05-23T10:35:00Z
```

## Building

### Requirements
- Python 3.9+
- Flask
- Requests
- Emoji (for enhanced formatting)

### Build Docker Image
```bash
docker build -t alert-translator:latest .
```

### Local Development
```bash
pip install -r requirements.txt
export NTFY_URLS='["http://localhost:8080"]'
export NTFY_TOPIC="test-alerts"
python app.py
```

## Testing

### Send Test Notification
```bash
curl -X POST http://localhost:5000/test
```

### Check Health
```bash
curl http://localhost:5000/health
```

### Simulate Alertmanager Webhook
```bash
curl -X POST http://localhost:5000/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "alerts": [{
      "status": "firing",
      "labels": {
        "alertname": "HighCPUUsage",
        "severity": "warning",
        "namespace": "production",
        "pod": "web-app-12345"
      },
      "annotations": {
        "summary": "High CPU usage detected",
        "description": "CPU usage is above 90%"
      },
      "startsAt": "2025-05-23T10:30:00Z"
    }]
  }'
```

## Troubleshooting

### Common Issues

**Notifications not appearing:**
1. Check NTFY server accessibility
2. Verify topic name matches your NTFY subscription
3. Check logs for connection errors

**Only some servers receiving notifications:**
1. Review logs for individual server errors
2. Verify all URLs are accessible from the container
3. Check network policies if running in Kubernetes

**Emoji not displaying:**
1. Ensure your NTFY client supports emoji
2. Check that the `emoji` package is installed

### Logs
```bash
# Docker
docker logs alert-translator

# Kubernetes
kubectl logs -f deployment/alert-translator -n monitoring
```

### Debug Mode
Set log level to DEBUG by modifying the logging configuration in `app.py`:
```python
logging.basicConfig(level=logging.DEBUG)
```

## Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌──────────────┐
│   Alertmanager  │───▶│ Alert Translator │───▶│  NTFY Server │
│                 │    │                  │    │      #1      │
│  - Prometheus   │    │ - Format alerts  │    └──────────────┘
│  - Rules        │    │ - Multi-server   │           │
│  - Routing      │    │ - Error handling │    ┌──────────────┐
└─────────────────┘    │ - Health checks  │───▶│  NTFY Server │
                       └──────────────────┘    │      #2      │
                                               └──────────────┘
                                                      │
                                               ┌──────────────┐
                                               │   Mobile     │
                                               │   Desktop    │
                                               │   Clients    │
                                               └──────────────┘
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## License

This project is open source. Feel free to use, modify, and distribute according to your needs.

---

**Made with ❤️ for better Kubernetes monitoring**
