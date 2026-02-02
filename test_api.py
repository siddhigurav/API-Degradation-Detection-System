#!/usr/bin/env python3
"""Test the API endpoints"""

import urllib.request
import json

# Test health endpoint
try:
    with urllib.request.urlopen('http://localhost:8000/health') as response:
        data = json.loads(response.read().decode())
        print(f'Health: {data}')
except Exception as e:
    print(f'Health error: {e}')

# Test alerts endpoint
try:
    with urllib.request.urlopen('http://localhost:8000/alerts') as response:
        data = json.loads(response.read().decode())
        print(f'Alerts response keys: {list(data.keys())}')
        print(f'Count: {data.get("count", "N/A")}')
        alerts = data.get('alerts', [])
        print(f'Found {len(alerts)} alerts')
        if alerts:
            alert = alerts[0]
            print(f'Sample alert: {alert["endpoint"]} - {alert["severity"]} - {len(alert.get("metrics_involved", []))} metrics')
except Exception as e:
    print(f'Alerts error: {e}')