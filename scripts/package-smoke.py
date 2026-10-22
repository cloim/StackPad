import json
import os
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
    # The desktop app forwards command lines to the engine; output arrives through pipes even though the app has no console.
    desktop = binary.parent / 'StackPad.exe'
    cli_checked = desktop.is_file()
    if cli_checked:
        environment = {**os.environ, 'STACKPAD_ENGINE': '127.0.0.1:48733', 'STACKPAD_CONFIG_DIR': folder.name}

        console = binary.parent / 'stackpad-cli.exe'
        assert console.is_file(), console

        def cli(*args, stdin=None, program=desktop):
            done = subprocess.run([str(program), *args], input=(stdin or '').encode('utf-8'), capture_output=True, env=environment, cwd=root, timeout=120)
            return done.returncode, done.stdout.decode('utf-8'), done.stderr.decode('utf-8')

        code, out, err = cli('padset', 'add', '스모크')
        assert code == 0, (code, out, err)
        code, out, err = cli('pad', 'add', '--name', '명령줄 검증', '--command', 'ping.exe 127.0.0.1 -n 999', '--padset', '스모크')
        assert code == 0, (code, out, err)
        assert json.loads(out)['pad']['components'][0]['cwd'] == str(root), out
        code, out, err = cli('pad', 'start', '명령줄 검증')
        assert code == 0, (code, out, err)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            pads = json.loads(cli('pad', 'list', '--padset', '스모크')[1])['pads']
            if pads[0]['status'] == 'running':
                break
            time.sleep(0.3)
        assert pads[0]['status'] == 'running', pads
        before = json.loads(cli('pad', 'show', '명령줄 검증', program=console)[1])
        code, out, err = cli('pad', 'update', '명령줄 검증', '--environment', 'production', program=console)
        assert code == 0, (code, out, err)
        after = json.loads(cli('pad', 'show', '명령줄 검증', program=console)[1])
        assert after['environment'] == after['input']['environment'] == 'production', after
        assert after['components'][0]['pid'] == before['components'][0]['pid'], (before, after)
        assert after['status'] == 'running', after
        assert cli('pad', 'delete', '명령줄 검증')[0] == 1
        assert cli('pad', 'stop', '명령줄 검증')[0] == 0
        assert cli('pad', 'update', '명령줄 검증', '--json', '-', stdin=json.dumps({'color': '#3b82f6'}))[0] == 0
        assert cli('pad', 'delete', '명령줄 검증')[0] == 0
        assert cli('padset', 'delete', '스모크')[0] == 0
        assert cli('pad', 'fly')[0] == 2
        assert 'padset list' in cli('help')[1]
        code, out, err = cli('padset', 'list', program=console)
        assert code == 0 and json.loads(out)['padsets'], (code, out, err)
        assert 'padset list' in cli(program=console)[1]
        # PowerShell waits for a console program even when its output goes straight into a variable.
        script = f"$o = & '{console}' version; if ($LASTEXITCODE -ne 0 -or -not ($o -join '' | ConvertFrom-Json).engine) {{ exit 9 }}"
        assert subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script], env=environment, stdin=subprocess.DEVNULL, capture_output=True, timeout=60).returncode == 0
        offline = subprocess.run([str(desktop), 'padset', 'list'], capture_output=True, env={**environment, 'STACKPAD_ENGINE': '127.0.0.1:1'}, timeout=30)
        assert offline.returncode == 3 and offline.stderr, offline
    # The tray quits the engine with the token it wrote into the data folder.
    token = (Path(folder.name) / 'control-token').read_text('utf-8')
    assert client.post('/api/engine/shutdown', json={}, headers={'X-StackPad-Control': 'wrong'}).status_code == 403
    assert client.post('/api/engine/shutdown', json={}, headers={'X-StackPad-Control': token}).status_code == 200
    psutil.Process(pid).wait(timeout=10)
    print('PACKAGE PASS: standalone executable, embedded SPA/assets, signed-in session, Windows native command, full process-tree stop, tray shutdown token'
          + (', desktop command line' if cli_checked else ''), flush=True)
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
