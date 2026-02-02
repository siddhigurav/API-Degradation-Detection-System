#!/usr/bin/env python3
"""Test app import"""

import sys
sys.path.insert(0, '.')
print('Importing app...')
from src.alerter import app
print('App imported successfully')
routes = [r for r in app.routes if hasattr(r, 'path')]
print(f'App has {len(routes)} routes')
for route in routes[:5]:
    print(f'  {route.path}')