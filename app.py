from flask import Flask, request, jsonify
import requests
import os
import re
import json
import logging

app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Parse NTFY URLs - supports JSON array or comma-separated values
def parse_ntfy_urls():
    urls_env = os.getenv('NTFY_URLS', os.getenv('NTFY_URL', 'http://ntfy.ntfy.svc.cluster.local'))

    # Try to parse as JSON array first
    try:
        urls = json.loads(urls_env)
        if isinstance(urls, list):
            return urls
    except (json.JSONDecodeError, TypeError):
        pass

    # Fall back to comma-separated values
    urls = [url.strip() for url in urls_env.split(',') if url.strip()]
    return urls

NTFY_URLS = parse_ntfy_urls()
NTFY_TOPIC = os.getenv('NTFY_TOPIC', 'kubernetes-alerts')

# Validate URLs on startup
logger.info(f"Configured NTFY servers: {NTFY_URLS}")
logger.info(f"Using topic: {NTFY_TOPIC}")

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
    return re.sub(r'[^\x00-\x7F]+', '', value)

def send_to_ntfy_servers(title, message, alert_config, tags):
    """Send notification to all configured NTFY servers"""
    headers = {
        'Title': clean_header_value(title),
        'Priority': alert_config['priority'],
        'Tags': clean_header_value(','.join(tags))
    }

    success_count = 0
    for ntfy_url in NTFY_URLS:
        try:
            url = f"{ntfy_url.rstrip('/')}/{NTFY_TOPIC}"
            response = requests.post(url, headers=headers, data=message, timeout=10)
            response.raise_for_status()
            logger.info(f"Successfully sent alert to {ntfy_url}")
            success_count += 1
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to send alert to {ntfy_url}: {e}")
        except Exception as e:
            logger.error(f"Unexpected error sending to {ntfy_url}: {e}")

    return success_count

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        alert_data = request.json
        if not alert_data:
            return jsonify({'error': 'No JSON data received'}), 400

        alerts_processed = 0
        total_notifications_sent = 0

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
            success_count = send_to_ntfy_servers(title, message, alert_config, tags)

            alerts_processed += 1
            total_notifications_sent += success_count

            logger.info(f"Processed alert '{alert.get('labels', {}).get('alertname', 'Unknown')}' - sent to {success_count}/{len(NTFY_URLS)} servers")

        return jsonify({
            'status': 'success',
            'alerts_processed': alerts_processed,
            'notifications_sent': total_notifications_sent,
            'servers_configured': len(NTFY_URLS)
        }), 200

    except Exception as e:
        logger.error(f"Error processing webhook: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'servers_configured': len(NTFY_URLS),
        'ntfy_servers': NTFY_URLS,
        'topic': NTFY_TOPIC
    }), 200

@app.route('/test', methods=['POST'])
def test_notification():
    """Test endpoint to send a sample notification"""
    try:
        test_title = "Alert Translator Test"
        test_message = "🧪 This is a test notification from the alert-translator service"
        test_config = get_alert_config('info')
        test_tags = ['test', 'alert-translator']

        success_count = send_to_ntfy_servers(test_title, test_message, test_config, test_tags)

        return jsonify({
            'status': 'success',
            'message': 'Test notification sent',
            'sent_to_servers': success_count,
            'total_servers': len(NTFY_URLS)
        }), 200

    except Exception as e:
        logger.error(f"Error sending test notification: {e}")
        return jsonify({'error': 'Failed to send test notification'}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
