"""Show a Windows folder chooser in a detached, hidden-console STA process."""
import base64
import json
import os
import tempfile
import threading
import time
from pathlib import Path

from i18n import system_text

import psutil


def select_folder(current, description='설정과 로그를 저장할 빈 폴더를 선택해 주세요.'):
    if os.name != 'nt':
        raise ValueError('Windows PC에서 폴더를 선택해 주세요.')
    from engine import powershell
    with tempfile.TemporaryDirectory(prefix='stackpad-folder-') as temporary:
        result_path = Path(temporary) / 'selection.json'
        initial = str(current).replace("'", "''")
        output = str(result_path).replace("'", "''")
        dialog = f"""$ErrorActionPreference='Stop'
try {{
  Add-Type -AssemblyName System.Windows.Forms
  [System.Windows.Forms.Application]::EnableVisualStyles()
  $owner=New-Object System.Windows.Forms.Form
  $owner.TopMost=$true; $owner.ShowInTaskbar=$false; $owner.Opacity=0
  $owner.Show()
  $dialog=New-Object System.Windows.Forms.FolderBrowserDialog
  $dialog.Description='{system_text(description)}'
  $dialog.SelectedPath='{initial}'
  $dialog.ShowNewFolderButton=$true
  $selected=$null
  if($dialog.ShowDialog($owner) -eq [System.Windows.Forms.DialogResult]::OK) {{$selected=$dialog.SelectedPath}}
  $dialog.Dispose(); $owner.Close(); $owner.Dispose()
  $result=@{{path=$selected}}
}} catch {{ $result=@{{error='폴더 선택 창을 열지 못했습니다. 다시 시도해 주세요.'}} }}
[IO.File]::WriteAllText('{output}.tmp', ($result | ConvertTo-Json -Compress), (New-Object Text.UTF8Encoding($false)))
[IO.File]::Move('{output}.tmp', '{output}')
"""
        encoded = base64.b64encode(dialog.encode('utf-16-le')).decode('ascii')
        launched = json.loads(powershell(f"""$s=New-CimInstance -CimClass (Get-CimClass Win32_ProcessStartup) -Property @{{ShowWindow=[uint16]0}} -ClientOnly
$r=Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{{CommandLine='powershell.exe -NoProfile -STA -EncodedCommand {encoded}';ProcessStartupInformation=$s}}
$r | Select-Object ProcessId,ReturnValue | ConvertTo-Json -Compress
"""))
        if launched['ReturnValue']:
            raise ValueError('폴더 선택 창을 다시 열어 주세요.')
        try:
            process = psutil.Process(launched['ProcessId'])
        except psutil.NoSuchProcess:
            process = None
        wait = threading.Event()
        try:
            deadline = time.monotonic() + 300
            while not result_path.exists():
                if time.monotonic() >= deadline or process is None or not process.is_running():
                    raise ValueError('폴더 선택을 다시 시도해 주세요.')
                wait.wait(.2)
            result = json.loads(result_path.read_text('utf-8'))
            if result.get('error'):
                raise ValueError(result['error'])
            return result['path']
        finally:
            try:
                if process is not None and process.is_running():
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except psutil.TimeoutExpired:
                        process.kill()
            except psutil.NoSuchProcess:
                pass
