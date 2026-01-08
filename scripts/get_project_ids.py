#!/usr/bin/env python3
"""Get project IDs for projects matching a name pattern."""
import os
import sys
import time
import hashlib
import base64
import requests

USER_ID = os.environ.get('QC_USER_ID')
API_TOKEN = os.environ.get('QC_API_TOKEN')

def get_auth_headers():
    timestamp = str(int(time.time()))
    hash_str = f"{API_TOKEN}:{timestamp}"
    hash_digest = hashlib.sha256(hash_str.encode()).hexdigest()
    auth = base64.b64encode(f"{USER_ID}:{hash_digest}".encode()).decode()
    return {
        'Authorization': f'Basic {auth}',
        'Timestamp': timestamp
    }

def get_projects(pattern=None):
    resp = requests.get(
        'https://www.quantconnect.com/api/v2/projects/read',
        headers=get_auth_headers()
    )
    data = resp.json()
    projects = data.get('projects', [])

    if pattern:
        projects = [p for p in projects if pattern.lower() in p['name'].lower()]

    for p in projects:
        print(f"{p['projectId']}: {p['name']}")

if __name__ == '__main__':
    pattern = sys.argv[1] if len(sys.argv) > 1 else None
    get_projects(pattern)
