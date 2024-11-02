# roles/log-stack/files/alert-translator/app.py
from flask import Flask, request, jsonify
from emoji import emojize
import requests
import os

app = Flask(__name__)

NTFY_URL = os.getenv('NTFY_URL', 'http://ntfy.ntfy.svc.cluster.local')
NTFY_TOPIC = os.getenv('NTFY_TOPIC', 'kubernetes-alerts')

SEVERITY_CONFIGS = {
    'critical': {
        'priority': 'urgent',
        'emoji': ':rotating_light:',
        'tags': ['warning', 'skull']
    },
    'warning': {
        'priority': 'high',
        'emoji': ':warning:',
        'tags': ['warning']
    },
    'info': {
        'priority': 'default',
        'emoji': ':information:',
        'tags': ['bell']
    }
}

def get_alert_config(severity):
    return SEVERITY_CONFIGS.get(severity.lower(), SEVERITY_CONFIGS['info'])

@app.route('/webhook', methods=['POST'])
def webhook():
    alert_data = request.json
    
    for alert in alert_data.get('alerts', []):
        severity = alert.get('labels', {}).get('severity', 'info')
        alert_config = get_alert_config(severity)
        
        status = alert.get('status', 'firing')
        if status == 'resolved':
            title = f"{alert_config['emoji']} Alert Resolved: {alert.get('labels', {}).get('alertname', 'Unknown Alert')}"
            tags = ['resolved', 'heavy_check_mark']
        else:
            title = f"{alert_config['emoji']} {alert.get('labels', {}).get('alertname', 'Unknown Alert')}"
            tags = alert_config['tags']

        # Build a detailed message
        message = []
        message.append(f"🏷️ Status: {status.upper()}")
        
        # Add summary if available
        if 'summary' in alert.get('annotations', {}):
            message.append(f"📝 Summary: {alert['annotations']['summary']}")
        
        # Add description if available
        if 'description' in alert.get('annotations', {}):
            message.append(f"ℹ️ Description: {alert['annotations']['description']}")
        
        # Add important labels
        labels = alert.get('labels', {})
        if 'namespace' in labels:
            message.append(f"🔍 Namespace: {labels['namespace']}")
        if 'pod' in labels:
            message.append(f"📦 Pod: {labels['pod']}")
        if 'instance' in labels:
            message.append(f"🖥️ Instance: {labels['instance']}")
        
        # Add timing information
        message.append(f"⏰ Started: {alert.get('startsAt', 'Unknown')}")
        if status == 'resolved':
            message.append(f"✅ Resolved: {alert.get('endsAt', 'Unknown')}")

        # Send to ntfy
        ntfy_data = {
            'topic': NTFY_TOPIC,
            'title': title,
            'message': '\n'.join(message),
            'priority': alert_config['priority'],
            'tags': ','.join(tags)
        }
        
        requests.post(f"{NTFY_URL}/{NTFY_TOPIC}", 
                     headers={
                         'Title': title,
                         'Priority': alert_config['priority'],
                         'Tags': ','.join(tags)
                     },
                     data='\n'.join(message))

    return jsonify({'status': 'success'}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)