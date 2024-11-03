from flask import Flask, request, jsonify
import requests
import os
import re

app = Flask(__name__)

NTFY_URL = os.getenv('NTFY_URL', 'http://ntfy.ntfy.svc.cluster.local')
NTFY_TOPIC = os.getenv('NTFY_TOPIC', 'kubernetes-alerts')

SEVERITY_CONFIGS = {
    'critical': {
        'priority': 'urgent',
        'emoji': 'CRITICAL',  # Removed emoji from header
        'tags': ['critical', 'skull'],
        'prefix': 'CRITICAL'
    },
    'warning': {
        'priority': 'high',
        'emoji': 'WARNING',  # Removed emoji from header
        'tags': ['warning'],
        'prefix': 'WARNING'
    },
    'info': {
        'priority': 'default',
        'emoji': 'INFO',  # Removed emoji from header
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
    # Remove emoji and other non-ASCII characters
    return re.sub(r'[^\x00-\x7F]+', '', value)

@app.route('/webhook', methods=['POST'])
def webhook():
    alert_data = request.json
    
    for alert in alert_data.get('alerts', []):
        severity = alert.get('labels', {}).get('severity', 'info')
        alert_config = get_alert_config(severity)
        
        status = alert.get('status', 'firing')
        
        # Build title (emojis will go in the message body instead)
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

        # Clean header values and send to ntfy
        requests.post(f"{NTFY_URL}/{NTFY_TOPIC}", 
                     headers={
                         'Title': clean_header_value(title),
                         'Priority': alert_config['priority'],
                         'Tags': clean_header_value(','.join(tags))
                     },
                     data='\n'.join(message_parts))

    return jsonify({'status': 'success'}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)