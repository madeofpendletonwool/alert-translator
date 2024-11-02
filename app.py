# roles/log-stack/files/alert-translator/app.py
from flask import Flask, request, jsonify
import requests
import os

app = Flask(__name__)

NTFY_URL = os.getenv('NTFY_URL', 'http://ntfy.ntfy.svc.cluster.local')
NTFY_TOPIC = os.getenv('NTFY_TOPIC', 'kubernetes-alerts')

SEVERITY_CONFIGS = {
    'critical': {
        'priority': 'urgent',
        'emoji': '🚨',
        'tags': ['critical', 'skull'],
        'prefix': 'CRITICAL'
    },
    'warning': {
        'priority': 'high',
        'emoji': '⚠️',
        'tags': ['warning'],
        'prefix': 'WARNING'
    },
    'info': {
        'priority': 'default',
        'emoji': 'ℹ️',
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

@app.route('/webhook', methods=['POST'])
def webhook():
    alert_data = request.json
    
    for alert in alert_data.get('alerts', []):
        severity = alert.get('labels', {}).get('severity', 'info')
        alert_config = get_alert_config(severity)
        
        status = alert.get('status', 'firing')
        
        # Build title
        if status == 'resolved':
            title = f"{STATUS_EMOJIS['resolved']} RESOLVED: {alert.get('labels', {}).get('alertname', 'Unknown Alert')}"
            tags = ['resolved', 'check']
        else:
            title = f"{alert_config['emoji']} {alert_config['prefix']}: {alert.get('labels', {}).get('alertname', 'Unknown Alert')}"
            tags = alert_config['tags']

        # Build message with better formatting
        message_parts = []
        
        # Status line with emoji
        message_parts.append(f"{STATUS_EMOJIS[status]} Status: {status.upper()}")
        
        # Summary and Description with proper spacing
        if 'summary' in alert.get('annotations', {}):
            message_parts.append(f"\n📝 Summary:\n{alert['annotations']['summary']}")
        
        if 'description' in alert.get('annotations', {}):
            message_parts.append(f"\n📋 Description:\n{alert['annotations']['description']}")
        
        # Important labels section
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
        
        # Duration if available
        if 'for' in alert:
            message_parts.append(f"\n⏱️ Duration: {format_duration(alert['for'])}")
            
        # Timing information
        message_parts.append(f"\n⏰ Started: {alert.get('startsAt', 'Unknown')}")
        if status == 'resolved':
            message_parts.append(f"✅ Resolved: {alert.get('endsAt', 'Unknown')}")
            
        # Add runbook URL if available
        if 'runbook_url' in alert.get('annotations', {}):
            message_parts.append(f"\n📚 Runbook: {alert['annotations']['runbook_url']}")

        # Send to ntfy
        requests.post(f"{NTFY_URL}/{NTFY_TOPIC}", 
                     headers={
                         'Title': title,
                         'Priority': alert_config['priority'],
                         'Tags': ','.join(tags)
                     },
                     data='\n'.join(message_parts))

    return jsonify({'status': 'success'}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)