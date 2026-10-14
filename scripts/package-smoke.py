import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx
import psutil
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from engine import powershell
import ui_session

root = Path(__file__).resolve().parents[1]
binary = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else root / 'release/StackPad/StackPadEngine.exe'
folder = tempfile.TemporaryDirectory(prefix='stackpad-package-')
session = ui_session.seed(folder.name)
pid = None
try:
    line = subprocess.list2cmdline([str(binary), '--data-dir', folder.name, '--port', '48733']).replace("'", "''")
    working = str(binary.parent).replace("'", "''")
    script = f"""$ErrorActionPreference='Stop'
$s=New-CimInstance -CimClass (Get-CimClass Win32_ProcessStartup) -Property @{{ShowWindow=[uint16]0}} -ClientOnly
$r=Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{{CommandLine='{line}';CurrentDirectory='{working}';ProcessStartupInformation=$s}}
$r | Select-Object ProcessId,ReturnValue | ConvertTo-Json -Compress
"""
    result = json.loads(powershell(script))
    assert result['ReturnValue'] == 0, result
    pid = result['ProcessId']
    created = psutil.Process(pid).create_time()
    base = 'http://127.0.0.1:48733'
    client = httpx.Client(base_url=base, headers={'Origin': base}, timeout=20)
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            health = client.get('/api/health')
            if health.status_code == 200:
                break
        except httpx.TransportError:
            pass
        time.sleep(0.3)
    else:
        raise AssertionError('Packaged engine did not become ready')
    assert health.json()['app'] == 'stackpad'
    assert '<title>StackPad</title>' in client.get('/').text
    assert client.get('/settings').status_code == 200
    assert client.get('/api/services').status_code == 401
    client.cookies.set('stackpad_session', session)
    assert client.get('/api/auth').json()['authenticated']
    service = client.post('/api/services', json={'name': '패키지 실행 검증', 'command': 'ping.exe 127.0.0.1 -n 999', 'cwd': str(root), 'port': None, 'health_url': '', 'color': '#97f7da', 'slot': 0, 'autostart': False})
    assert service.status_code == 200, service.text
    service_id = service.json()['id']
    start = client.post(f'/api/services/{service_id}/start')
    assert start.status_code == 200, start.text
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        live = client.get('/api/services').json()['services'][0]
        if live['status'] == 'running':
            break
        time.sleep(0.3)
    assert live['status'] == 'running', live
    owned_pid = live['pid']
    stop = client.post(f'/api/services/{service_id}/stop')
    assert stop.status_code == 200, stop.text
    assert not psutil.pid_exists(owned_pid)
    assert client.get('/api/services').json()['services'][0]['status'] == 'stopped'
    assert client.delete(f'/api/services/{service_id}').status_code == 200
    # The tray quits the engine with the token it wrote into the data folder.
    token = (Path(folder.name) / 'control-token').read_text('utf-8')
    assert client.post('/api/engine/shutdown', json={}, headers={'X-StackPad-Control': 'wrong'}).status_code == 403
    assert client.post('/api/engine/shutdown', json={}, headers={'X-StackPad-Control': token}).status_code == 200
    psutil.Process(pid).wait(timeout=10)
    print('PACKAGE PASS: standalone executable, embedded SPA/assets, signed-in session, Windows native command, full process-tree stop, tray shutdown token', flush=True)
finally:
    if pid and psutil.pid_exists(pid):
        process = psutil.Process(pid)
        if abs(process.create_time() - created) < 0.01:
            targets = [process, *process.children(recursive=True)]
            subprocess.run(['taskkill.exe', '/F', '/T', '/PID', str(pid)], stdin=subprocess.DEVNULL, capture_output=True, creationflags=0x08000000, check=True)
            _, alive = psutil.wait_procs(targets, timeout=10)
            assert not any(target.is_running() for target in alive), 'Packaged fixture must exit before cleaning its logs'
    if 'client' in locals():
        client.close()
    folder.cleanup()
