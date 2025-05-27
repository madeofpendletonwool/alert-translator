from flask import Flask, request, jsonify
import requests
import os
import re
import json
import logging
import yaml
from requests.auth import HTTPBasicAuth
import base64

app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Default configuration
DEFAULT_CONFIG = {
    'servers': [
        {
            'name': 'default',
            'url': 'http://ntfy.ntfy.svc.cluster.local',
            'auth': None
        }
    ],
    'topic': 'kubernetes-alerts'
}

def substitute_env_vars(text):
    """Substitute environment variables in text using ${VAR} syntax"""
    import re
    def replace_var(match):
        var_name = match.group(1)
        return os.getenv(var_name, match.group(0))  # Return original if env var not found

    return re.sub(r'\$\{([^}]+)\}', replace_var, text)

def load_config():
    """Load configuration from file or environment variables"""
    config_file = os.getenv('CONFIG_FILE', '/etc/alert-translator/config.yaml')

    # Try to load from config file first
    if os.path.exists(config_file):
        try:
            with open(config_file, 'r') as f:
                config_text = f.read()

            # Substitute environment variables
            config_text = substitute_env_vars(config_text)
            logger.debug(f"Config after env substitution: {config_text}")

            # Parse YAML
            config = yaml.safe_load(config_text)
            logger.info(f"Loaded configuration from {config_file}")
            return config
        except Exception as e:
            logger.error(f"Failed to load config file {config_file}: {e}")

    # Fall back to environment variables for backward compatibility
    config = DEFAULT_CONFIG.copy()

    # Parse NTFY URLs - supports JSON array or comma-separated values
    urls_env = os.getenv('NTFY_URLS', os.getenv('NTFY_URL'))
    if urls_env:
        try:
            urls = json.loads(urls_env)
            if isinstance(urls, list):
                config['servers'] = [{'name': f'server_{i}', 'url': url, 'auth': None} for i, url in enumerate(urls)]
            else:
                raise ValueError("Not a list")
        except (json.JSONDecodeError, TypeError, ValueError):
            # Fall back to comma-separated values
            urls = [url.strip() for url in urls_env.split(',') if url.strip()]
            config['servers'] = [{'name': f'server_{i}', 'url': url, 'auth': None} for i, url in enumerate(urls)]

    # Override topic if set in environment
    if os.getenv('NTFY_TOPIC'):
        config['topic'] = os.getenv('NTFY_TOPIC')

    logger.info("Loaded configuration from environment variables")
    return config

# Load configuration
CONFIG = load_config()

# Validate configuration on startup
logger.info(f"Configured NTFY servers:")
for server in CONFIG['servers']:
    auth_info = "with auth" if server.get('auth') else "no auth"
    logger.info(f"  - {server['name']}: {server['url']} ({auth_info})")
logger.info(f"Using topic: {CONFIG['topic']}")

def send_startup_notification():
    """Send a startup notification to confirm the service is running"""
    try:
        # Get server info for the message
        server_list = []
        for server in CONFIG['servers']:
            auth_status = "🔐 with auth" if server.get('auth') else "🔓 no auth"
            server_list.append(f"• {server.get('name', 'unnamed')}: {server['url']} ({auth_status})")

        title = "Alert Translator Started"
        message_parts = [
            "✅ Alert Translator service is now online and ready to receive alerts!",
            f"\n📡 Configured Servers ({len(CONFIG['servers'])}):",
            "\n".join(server_list),
            f"\n📢 Topic: {CONFIG['topic']}",
            f"\n🕐 Started at: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}",
            "\n🎯 You will now receive Kubernetes alerts from Prometheus/Alertmanager on this topic."
        ]

        message = '\n'.join(message_parts)
        alert_config = get_alert_config('info')
        tags = ['startup', 'alert-translator', 'system']

        success_count, results = send_to_ntfy_servers(title, message, alert_config, tags)

        if success_count > 0:
            logger.info(f"Startup notification sent successfully to {success_count}/{len(CONFIG['servers'])} servers")
        else:
            logger.warning("Failed to send startup notification to any servers")

        # Log individual results
        for result in results:
            if result['status'] == 'success':
                logger.info(f"Startup notification delivered to {result['server']}")
            else:
                logger.error(f"Failed to deliver startup notification to {result['server']}: {result.get('error', 'Unknown error')}")

    except Exception as e:
        logger.error(f"Error sending startup notification: {e}")

SEVERITY_CONFIGS = {
    'critical': {
        'priority': 'urgent',
        'emoji': 'CRITICAL',
        'tags': ['critical', 'skull'],
        'prefix': 'CRITICAL'
    },
    'warning': {
        'priority': 'high',
        'emoji': 'WARNING',
        'tags': ['warning'],
        'prefix': 'WARNING'
    },
    'info': {
        'priority': 'default',
        'emoji': 'INFO',
        'tags': ['info'],
        'prefix': 'INFO'
    }
}

STATUS_EMOJIS = {
    'firing': '🔥',
    'resolved': '✅'
}

def format_duration(duration_str):
    """Format duration strings to be more readable"""
    if 'h' in duration_str:
        hours = duration_str.replace('h', '')
        return f"{hours} hours"
    if 'm' in duration_str:
        minutes = duration_str.replace('m', '')
        return f"{minutes} minutes"
    return duration_str

def get_alert_config(severity):
    return SEVERITY_CONFIGS.get(severity.lower(), SEVERITY_CONFIGS['info'])

def clean_header_value(value):
    """Remove emoji and non-ASCII characters from header values"""
    # Strip whitespace and remove non-ASCII characters
    cleaned = re.sub(r'[^\x00-\x7F]+', '', str(value)).strip()
    return cleaned

def get_auth_headers(auth_config):
    """Generate authentication headers based on auth config"""
    if not auth_config:
        return {}

    auth_type = auth_config.get('type', '').lower()

    if auth_type == 'basic':
        username = auth_config.get('username')
        password = auth_config.get('password')
        if username and password:
            credentials = base64.b64encode(f"{username}:{password}".encode()).decode()
            return {'Authorization': f'Basic {credentials}'}

    elif auth_type == 'token':
        token = auth_config.get('token')
        if token:
            return {'Authorization': f'Bearer {token}'}

    return {}

def send_to_ntfy_servers(title, message, alert_config, tags):
    """Send notification to all configured NTFY servers"""
    base_headers = {
        'Title': clean_header_value(title),
        'Priority': alert_config['priority'],
        'Tags': clean_header_value(','.join(tags)),
        'Content-Type': 'text/plain; charset=utf-8'
    }

    success_count = 0
    results = []

    for server in CONFIG['servers']:
        server_name = server.get('name', 'unnamed')
        server_url = server['url']

        try:
            # Prepare headers with authentication
            headers = base_headers.copy()
            auth_headers = get_auth_headers(server.get('auth'))
            headers.update(auth_headers)

            url = f"{server_url.rstrip('/')}/{CONFIG['topic']}"
            response = requests.post(url, headers=headers, data=message.encode('utf-8'), timeout=10)
            response.raise_for_status()

            logger.info(f"Successfully sent alert to {server_name} ({server_url})")
            success_count += 1
            results.append({'server': server_name, 'status': 'success', 'url': server_url})

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to send alert to {server_name} ({server_url}): {e}")
            results.append({'server': server_name, 'status': 'failed', 'error': str(e), 'url': server_url})
        except Exception as e:
            logger.error(f"Unexpected error sending to {server_name} ({server_url}): {e}")
            results.append({'server': server_name, 'status': 'error', 'error': str(e), 'url': server_url})

    return success_count, results

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        alert_data = request.json
        if not alert_data:
            return jsonify({'error': 'No JSON data received'}), 400

        alerts_processed = 0
        total_notifications_sent = 0
        all_results = []

        for alert in alert_data.get('alerts', []):
            severity = alert.get('labels', {}).get('severity', 'info')
            alert_config = get_alert_config(severity)

            status = alert.get('status', 'firing')

            # Build title
            if status == 'resolved':
                title = f"RESOLVED: {alert.get('labels', {}).get('alertname', 'Unknown Alert')}"
                tags = ['resolved', 'check']
            else:
                title = f"{alert_config['prefix']}: {alert.get('labels', {}).get('alertname', 'Unknown Alert')}"
                tags = alert_config['tags']

            # Build message with emojis in the body
            message_parts = []

            # Add status emoji at the start of the message
            message_parts.append(f"{STATUS_EMOJIS[status]} Status: {status.upper()}")

            if 'summary' in alert.get('annotations', {}):
                message_parts.append(f"\n📝 Summary:\n{alert['annotations']['summary']}")

            if 'description' in alert.get('annotations', {}):
                message_parts.append(f"\n📋 Description:\n{alert['annotations']['description']}")

            labels = alert.get('labels', {})
            label_parts = []

            if 'namespace' in labels:
                label_parts.append(f"📍 Namespace: {labels['namespace']}")
            if 'pod' in labels:
                label_parts.append(f"📦 Pod: {labels['pod']}")
            if 'instance' in labels:
                label_parts.append(f"🖥️ Instance: {labels['instance']}")
            if 'job' in labels:
                label_parts.append(f"⚙️ Job: {labels['job']}")

            if label_parts:
                message_parts.append("\n🏷️ Labels:\n" + "\n".join(label_parts))

            if 'for' in alert:
                message_parts.append(f"\n⏱️ Duration: {format_duration(alert['for'])}")

            message_parts.append(f"\n⏰ Started: {alert.get('startsAt', 'Unknown')}")
            if status == 'resolved':
                message_parts.append(f"✅ Resolved: {alert.get('endsAt', 'Unknown')}")

            if 'runbook_url' in alert.get('annotations', {}):
                message_parts.append(f"\n📚 Runbook: {alert['annotations']['runbook_url']}")

            # Send to all NTFY servers
            message = '\n'.join(message_parts)
            success_count, results = send_to_ntfy_servers(title, message, alert_config, tags)

            alerts_processed += 1
            total_notifications_sent += success_count
            all_results.extend(results)

            logger.info(f"Processed alert '{alert.get('labels', {}).get('alertname', 'Unknown')}' - sent to {success_count}/{len(CONFIG['servers'])} servers")

        return jsonify({
            'status': 'success',
            'alerts_processed': alerts_processed,
            'notifications_sent': total_notifications_sent,
            'servers_configured': len(CONFIG['servers']),
            'results': all_results
        }), 200

    except Exception as e:
        logger.error(f"Error processing webhook: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    server_info = []
    for server in CONFIG['servers']:
        server_info.append({
            'name': server.get('name', 'unnamed'),
            'url': server['url'],
            'has_auth': bool(server.get('auth'))
        })

    return jsonify({
        'status': 'healthy',
        'servers_configured': len(CONFIG['servers']),
        'servers': server_info,
        'topic': CONFIG['topic']
    }), 200

@app.route('/test', methods=['POST'])
def test_notification():
    """Test endpoint to send a sample notification"""
    try:
        test_title = "Alert Translator Test"
        test_message = "🧪 This is a test notification from the alert-translator service"
        test_config = get_alert_config('info')
        test_tags = ['test', 'alert-translator']

        success_count, results = send_to_ntfy_servers(test_title, test_message, test_config, test_tags)

        return jsonify({
            'status': 'success',
            'message': 'Test notification sent',
            'sent_to_servers': success_count,
            'total_servers': len(CONFIG['servers']),
            'results': results
        }), 200

    except Exception as e:
        logger.error(f"Error sending test notification: {e}")
        return jsonify({'error': 'Failed to send test notification'}), 500

@app.route('/config', methods=['GET'])
def get_config():
    """Get current configuration (without sensitive data)"""
    safe_config = CONFIG.copy()

    # Remove sensitive authentication data
    safe_servers = []
    for server in safe_config['servers']:
        safe_server = {
            'name': server.get('name', 'unnamed'),
            'url': server['url'],
            'has_auth': bool(server.get('auth'))
        }
        if server.get('auth'):
            safe_server['auth_type'] = server['auth'].get('type', 'unknown')
        safe_servers.append(safe_server)

    safe_config['servers'] = safe_servers

    return jsonify(safe_config), 200

if __name__ == '__main__':
    # Send startup notification now that all functions are defined
    send_startup_notification()
    app.run(host='0.0.0.0', port=5000)
