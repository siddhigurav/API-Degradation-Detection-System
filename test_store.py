#!/usr/bin/env python3
"""Test AlertStore directly"""

import sys
sys.path.append('src')
from alerter import AlertStore

store = AlertStore()
alerts = store.get_all_alerts()
print(f'Store has {len(alerts)} alerts')

if alerts:
    print(f'First alert keys: {list(alerts[0].keys())}')
    print(f'First alert: {alerts[0]["endpoint"]} - {alerts[0]["severity"]}')
    print(f'Anomalous metrics: {alerts[0]["anomalous_metrics"]}')