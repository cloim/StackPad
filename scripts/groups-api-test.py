"""Exercise grouped HTTP operations against an isolated QA engine."""
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx

base = 'http://127.0.0.1:48732'
client = httpx.Client(base_url=base, headers={'Origin': base}, timeout=65)
assert client.get('/api/services').status_code == 401
assert client.post('/api/groups', json={}).status_code == 401
assert client.post('/api/setup', json={'password': 'StackPad-QA-Group-2026'}).status_code == 200
ports = []
for _ in range(2):
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        ports.append(probe.getsockname()[1])
components = []
for index, port in enumerate(ports):
    components.append({'name': ['QA backend', 'QA frontend'][index], 'command': subprocess.list2cmdline([sys.executable, '-m', 'http.server', str(port), '--bind', '127.0.0.1']), 'cwd': str(Path.cwd()), 'port': port, 'health_url': f'http://127.0.0.1:{port}/'})
pad_values = {'name': 'QA app', 'components': components, 'slot': 0, 'color': '#7db5eb', 'wait_ready': True, 'autostart': False}
response = client.post('/api/pads', json=pad_values)
assert response.status_code == 200
group_id = response.json()['id']
ids = client.get('/api/services').json()['groups'][0]['member_ids']
group_values = {'name': 'QA app', 'member_ids': ids, 'slot': 0, 'color': '#7db5eb', 'wait_ready': True, 'autostart': False}
assert client.get('/api/services').json()['groups'][0]['member_ids'] == ids
assert client.post(f'/api/groups/{group_id}/start').status_code == 200
data = client.get('/api/services').json()['services']
assert all(s['pid'] and s['slot'] == 0 for s in data)
assert all(s['color'] == '#7db5eb' for s in data)
before_move = {s['id']: s['pid'] for s in data}
assert client.put(f'/api/pads/{group_id}/position', json={'slot': 9}).status_code == 200
data = client.get('/api/services').json()['services']
assert all(s['slot'] == 9 for s in data)
assert {s['id']: s['pid'] for s in data} == before_move
assert client.get('/api/services').json()['groups'][0]['slot'] == 9
assert client.put(f'/api/pads/{group_id}/position', json={'slot': 16}).status_code == 422
assert client.put(f'/api/pads/{group_id}', json=pad_values).status_code == 409
for port in ports:
    assert httpx.get(f'http://127.0.0.1:{port}/').status_code == 200
assert client.put(f'/api/groups/{group_id}', json=group_values).status_code == 409
assert client.delete(f'/api/groups/{group_id}').status_code == 409
assert client.delete(f'/api/services/{ids[0]}').status_code == 409
old_pid = data[0]['pid']
frontend_pid = next(s for s in data if s['id'] == ids[1])['pid']
assert client.post(f'/api/services/{ids[0]}/restart').status_code == 200
data = client.get('/api/services').json()['services']
assert next(s for s in data if s['id'] == ids[0])['pid'] != old_pid
assert next(s for s in data if s['id'] == ids[1])['pid'] == frontend_pid
assert client.get(f'/api/services/{ids[0]}/logs').json()['text']
assert client.post(f'/api/groups/{group_id}/stop').status_code == 200
assert not any(s['pid'] for s in client.get('/api/services').json()['services'])
for port in ports:
    with socket.socket() as probe:
        probe.settimeout(.5)
        assert probe.connect_ex(('127.0.0.1', port)) != 0
assert client.delete(f'/api/groups/{group_id}').status_code == 200
assert len({s['slot'] for s in client.get('/api/services').json()['services']}) == 2
assert client.get('/api/services').json()['groups'] == []
print('GROUP API PASS: atomic inline registration/shared color, ordered real process startup/readiness, running move with preserved PIDs, running guards, isolated restart/logs, full tree stop and group dissolution', flush=True)
