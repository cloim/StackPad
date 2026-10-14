"""Replace the StackPad binaries in release/StackPad with a staged build, keeping settings and running services.

Usage: python scripts/deploy-local-update.py <staged StackPad folder> [--replace-former]
--replace-former also stops the app under its former name, whose data the new engine copies on first start.
Services started by StackPad are separate processes and keep running; the new engine adopts them again.
"""
import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import httpx
import psutil

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / 'backend'))
from engine import powershell
from legacy import FORMER_NAME
from storage_location import resolve_data_dir

parser = argparse.ArgumentParser()
parser.add_argument('stage')
parser.add_argument('--replace-former', action='store_true')
args = parser.parse_args()
stage = Path(args.stage).resolve()
release = root / 'release/StackPad'
backup = root / '.jobs/backups' / time.strftime('%y%m%d-%H%M%S')
names = ['StackPad.exe', 'StackPadEngine.exe', 'README.md', 'LICENSE', 'portable']
for name in names:
    assert (stage / name).is_file(), f'Staged package is incomplete: {name}'

bootstrap = Path.home() / '.config' / 'stackpad'
former = Path.home() / '.config' / FORMER_NAME
source = bootstrap if (bootstrap / 'config.json').exists() or (bootstrap / 'storage-location.json').exists() else former
config = resolve_data_dir(source) / 'config.json'
before = json.loads(config.read_text('utf-8')) if config.exists() else None
backup.mkdir(parents=True, exist_ok=True)
if before is not None:
    shutil.copy2(config, backup / 'config.json')
for name in names:
    if (release / name).exists():
        shutil.copy2(release / name, backup / name)

targets = {str((release / name).resolve()).lower() for name in names[:2]}
former_names = {f'{FORMER_NAME}.exe'.lower(), 'service-deck-engine.exe'}
owned = []
for process in psutil.process_iter(['exe', 'name']):
    exe, name = process.info['exe'], (process.info['name'] or '').lower()
    if (exe and str(Path(exe).resolve()).lower() in targets) or (args.replace_former and name in former_names):
        owned.append(process)
engines = [p for p in owned if 'engine' in p.name().lower()]
for process in owned:
    if process not in engines and process.is_running():
        process.terminate()
for process in engines:
    # The engine tree only holds the engine itself; services were started detached through WMI.
    if process.is_running():
        subprocess.run(['taskkill.exe', '/F', '/T', '/PID', str(process.pid)], stdin=subprocess.DEVNULL, capture_output=True, check=False, creationflags=0x08000000)
_, alive = psutil.wait_procs(owned, timeout=15)
assert not any(p.is_running() for p in alive), 'Previous StackPad processes must exit before replacement'
print(f'Stopped {len(owned)} previous processes; backup in {backup}', flush=True)

release.mkdir(parents=True, exist_ok=True)
for name in names:
    shutil.copy2(stage / name, release / name)
desktop = str(release / 'StackPad.exe').replace("'", "''")
working = str(release).replace("'", "''")
launch = f"""$ErrorActionPreference='Stop'
$s=New-CimInstance -CimClass (Get-CimClass Win32_ProcessStartup) -Property @{{ShowWindow=[uint16]0}} -ClientOnly
$r=Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{{CommandLine='"{desktop}" --hidden';CurrentDirectory='{working}';ProcessStartupInformation=$s}}
$r | Select-Object ProcessId,ReturnValue | ConvertTo-Json -Compress
"""
result = json.loads(powershell(launch))
assert result['ReturnValue'] == 0, 'StackPad WMI start failed'
for _ in range(160):
    try:
        health = httpx.get('http://127.0.0.1:48731/api/health', timeout=2)
        if health.status_code == 200 and health.json().get('app') == 'stackpad':
            break
    except httpx.TransportError:
        pass
    time.sleep(0.25)
else:
    raise RuntimeError(f'The new engine did not become healthy; the previous files are in {backup}')

after_path = resolve_data_dir(bootstrap) / 'config.json'
if before is not None:
    after = json.loads(after_path.read_text('utf-8'))
    for key in ('services', 'groups', 'padsets'):
        assert [{k: v for k, v in item.items() if k not in ('runtime', 'error')} for item in after.get(key, [])] == \
               [{k: v for k, v in item.items() if k not in ('runtime', 'error')} for item in before.get(key, [])], f'{key} changed during deployment'
for name in names:
    assert (stage / name).read_bytes() == (release / name).read_bytes(), 'Deployed package must match the staged build'
print(f'DEPLOY PASS: engine {health.json()["version"]} healthy, pads preserved, data in {after_path.parent}', flush=True)
