# Alert Translator

A lightweight Flask middleware service that translates Kubernetes alerts from Prometheus/Alertmanager into beautifully formatted notifications for NTFY servers. Perfect for getting clean, emoji-rich alerts on your mobile device or desktop.

## Features

- 🚀 **Multi-Server Support**: Send alerts to multiple NTFY servers simultaneously
- 🔐 **Authentication Support**: Basic auth and token-based authentication per server
- 🎨 **Rich Formatting**: Clean, emoji-enhanced notifications with proper severity levels
- 🏷️ **Smart Labeling**: Automatically extracts and formats Kubernetes labels (namespace, pod, instance, job)
- ⚡ **Multiple Severity Levels**: Critical, Warning, and Info alerts with appropriate priorities
- 🔄 **Resolution Tracking**: Handles both firing and resolved alert states
- 📊 **Health Monitoring**: Built-in health check and test endpoints
- 🛡️ **Error Handling**: Robust error handling with detailed logging
- 🐳 **Container Ready**: Lightweight Python-based Docker container
- ⚙️ **Flexible Configuration**: YAML config files or environment variables

## Quick Start

### Docker Run (Environment Variables)

```bash
docker run -d \
  --name alert-translator \
  -p 5000:5000 \
  -e NTFY_URLS='["http://ntfy.ntfy.svc.cluster.local", "https://ntfy.example.com"]' \
  -e NTFY_TOPIC="k8s-alerts" \
  your-registry/alert-translator:latest
```

### Docker Run (Config File)

```bash
# Create config file
cat > config.yaml << EOF
topic: "kubernetes-alerts"
servers:
  - name: "internal-ntfy"
    url: "http://ntfy.ntfy.svc.cluster.local"
  - name: "external-ntfy"
    url: "https://ntfy.example.com"
    auth:
      type: "basic"
      username: "myuser"
      password: "mypass"
EOF

# Run with config file
docker run -d \
  --name alert-translator \
  -p 5000:5000 \
  -v $(pwd)/config.yaml:/etc/alert-translator/config.yaml \
  -e CONFIG_FILE="/etc/alert-translator/config.yaml" \
  your-registry/alert-translator:latest
```

## Configuration

### Method 1: YAML Configuration File (Recommended)

Create a `config.yaml` file:

```yaml
# Global topic for all servers
topic: "kubernetes-alerts"

# List of NTFY servers
servers:
  # Internal server (no authentication)
  - name: "internal-ntfy"
    url: "http://ntfy.ntfy.svc.cluster.local"

  # External server with basic authentication
  - name: "external-ntfy"
    url: "https://ntfy.example.com"
    auth:
      type: "basic"
      username: "your-username"
      password: "your-password"

  # Server with token authentication
  - name: "token-server"
    url: "https://ntfy.another.com"
    auth:
      type: "token"
      token: "tk_your_access_token_here"
```

Set the config file location:
```bash
export CONFIG_FILE="/path/to/config.yaml"
```

### Method 2: Environment Variables (Legacy Support)

| Variable | Description | Default | Example |
|----------|-------------|---------|---------|
| `CONFIG_FILE` | Path to YAML config file | `/etc/alert-translator/config.yaml` | `/app/config.yaml` |
| `NTFY_URLS` | NTFY server URLs (JSON array or comma-separated) | `http://ntfy.ntfy.svc.cluster.local` | `["http://server1", "http://server2"]` |
| `NTFY_URL` | Legacy single URL support | `http://ntfy.ntfy.svc.cluster.local` | `http://ntfy.example.com` |
| `NTFY_TOPIC` | NTFY topic name | `kubernetes-alerts` | `my-alerts` |

### NTFY_URLS Format Options

**JSON Array (Recommended):**
```bash
NTFY_URLS='["http://ntfy.ntfy.svc.cluster.local", "https://ntfy.example.com"]'
```

**Comma-Separated:**
```bash
NTFY_URLS="http://ntfy.ntfy.svc.cluster.local,https://ntfy.example.com"
```

**Single URL (Legacy):**
```bash
NTFY_URL="http://ntfy.ntfy.svc.cluster.local"
```

## Authentication Types

### Basic Authentication
```yaml
auth:
  type: "basic"
  username: "your-username"
  password: "your-password"
```

### Token Authentication
```yaml
auth:
  type: "token"
  token: "tk_your_access_token_here"
```

### No Authentication
Simply omit the `auth` section for servers that don't require authentication.

## Kubernetes Deployment

### ConfigMap and Secret Approach

```yaml
# ConfigMap for configuration
apiVersion: v1
kind: ConfigMap
metadata:
  name: alert-translator-config
  namespace: monitoring
data:
  config.yaml: |
    topic: "kubernetes-alerts"
    servers:
      - name: "internal-ntfy"
        url: "http://ntfy.ntfy.svc.cluster.local"
      - name: "external-ntfy"
        url: "https://ntfy.example.com"
        auth:
          type: "basic"
          username: "${EXTERNAL_NTFY_USERNAME}"
          password: "${EXTERNAL_NTFY_PASSWORD}"

---
# Secret for credentials
apiVersion: v1
kind: Secret
metadata:
  name: alert-translator-secrets
  namespace: monitoring
type: Opaque
data:
  # Base64 encoded credentials
  external-ntfy-username: bXl1c2VybmFtZQ==  # "myusername"
  external-ntfy-password: bXlwYXNzd29yZA==  # "mypassword"

---
# Deployment
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
        - name: CONFIG_FILE
          value: "/etc/alert-translator/config.yaml"
        - name: EXTERNAL_NTFY_USERNAME
          valueFrom:
            secretKeyRef:
              name: alert-translator-secrets
              key: external-ntfy-username
        - name: EXTERNAL_NTFY_PASSWORD
          valueFrom:
            secretKeyRef:
              name: alert-translator-secrets
              key: external-ntfy-password
        volumeMounts:
        - name: config-volume
          mountPath: /etc/alert-translator
          readOnly: true
        livenessProbe:
          httpGet:
            path: /health
            port: 5000
          initialDelaySeconds: 30
          periodSeconds: 30
        readinessProbe:
          httpGet:
            path: /health
            port: 5000
          initialDelaySeconds: 5
          periodSeconds: 10
      volumes:
      - name: config-volume
        configMap:
          name: alert-translator-config

---
# Service
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
  "servers_configured": 2,
  "results": [
    {"server": "internal-ntfy", "status": "success", "url": "http://ntfy.ntfy.svc.cluster.local"},
    {"server": "external-ntfy", "status": "success", "url": "https://ntfy.example.com"}
  ]
}
```

### GET /health
**Health check endpoint**

Response:
```json
{
  "status": "healthy",
  "servers_configured": 2,
  "servers": [
    {"name": "internal-ntfy", "url": "http://ntfy.ntfy.svc.cluster.local", "has_auth": false},
    {"name": "external-ntfy", "url": "https://ntfy.example.com", "has_auth": true}
  ],
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
  "total_servers": 2,
  "results": [
    {"server": "internal-ntfy", "status": "success", "url": "http://ntfy.ntfy.svc.cluster.local"},
    {"server": "external-ntfy", "status": "success", "url": "https://ntfy.example.com"}
  ]
}
```

### GET /config
**Get current configuration (without sensitive data)**

Response:
```json
{
  "topic": "kubernetes-alerts",
  "servers": [
    {"name": "internal-ntfy", "url": "http://ntfy.ntfy.svc.cluster.local", "has_auth": false},
    {"name": "external-ntfy", "url": "https://ntfy.example.com", "has_auth": true, "auth_type": "basic"}
  ]
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
```txt
Flask==3.0.0
requests==2.31.0
PyYAML==6.0.1
```

### Build Docker Image
```bash
# Create Dockerfile
cat > Dockerfile << EOF
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

RUN useradd --create-home --shell /bin/bash app && \
    chown -R app:app /app
USER app

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:5000/health || exit 1

EXPOSE 5000

CMD ["python", "app.py"]
EOF

# Build
docker build -t alert-translator:latest .
```

### Local Development
```bash
pip install -r requirements.txt
export CONFIG_FILE="config.yaml"
# or
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

### Check Configuration
```bash
curl http://localhost:5000/config
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
1. Check NTFY server accessibility: `curl http://your-ntfy-server/health`
2. Verify topic name matches your NTFY subscription
3. Check logs for connection errors
4. Verify authentication credentials if using auth

**Authentication errors:**
1. Check username/password are correct
2. Verify token is valid and has correct permissions
3. Check if the NTFY server has auth enabled
4. Review server logs for auth failures

**Only some servers receiving notifications:**
1. Review logs for individual server errors
2. Verify all URLs are accessible from the container
3. Check network policies if running in Kubernetes
4. Test each server individually

**Configuration errors:**
1. Validate YAML syntax: `python -c "import yaml; yaml.safe_load(open('config.yaml'))"`
2. Check environment variable substitution
3. Verify file permissions for config file
4. Check the `/config` endpoint for current configuration

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
│  - Prometheus   │    │ - Format alerts  │    │  (No Auth)   │
│  - Rules        │    │ - Multi-server   │    └──────────────┘
│  - Routing      │    │ - Authentication │           │
└─────────────────┘    │ - Error handling │    ┌──────────────┐
                       │ - Health checks  │───▶│  NTFY Server │
                       └──────────────────┘    │      #2      │
                                               │ (With Auth)  │
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
