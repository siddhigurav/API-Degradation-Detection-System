#!/usr/bin/env python3
"""Test script to check if the FastAPI app works"""

from src.alerter import app
print('App created successfully')
print(f'Routes: {[route.path for route in app.routes]}')

# Test the store
from src.alerter import AlertStore
store = AlertStore()
alerts = store.get_all_alerts()
print(f'Found {len(alerts)} alerts in store')