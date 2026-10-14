"""Check the real packaged desktop lifecycle, even on a locked desktop."""
import ctypes
import json
import sys
import time
from pathlib import Path
from ctypes import wintypes
import httpx
import psutil

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from engine import powershell
root = Path(__file__).resolve().parents[1]
binary = root / 'release/StackPad/StackPad.exe'
user32 = ctypes.windll.user32
user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
user32.FindWindowW.restype = wintypes.HWND
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
window = user32.FindWindowW(None, 'StackPad')
assert window, 'Desktop window not found'
pid = wintypes.DWORD()
user32.GetWindowThreadProcessId(window, ctypes.byref(pid))
assert Path(psutil.Process(pid.value).exe()).resolve() == binary.resolve()
created = psutil.Process(pid.value).create_time()
assert user32.IsWindowVisible(window), 'Initial window should be visible'
assert user32.PostMessageW(window, 0x0010, 0, 0)
deadline = time.monotonic() + 5
while user32.IsWindowVisible(window) and time.monotonic() < deadline:
    time.sleep(0.1)
assert not user32.IsWindowVisible(window), 'Close should hide to tray'
assert psutil.Process(pid.value).create_time() == created, 'Close should keep desktop process'
assert httpx.get('http://127.0.0.1:48731/api/health').json()['app'] == 'stackpad'
line = f'"{binary}"'.replace("'", "''")
working = str(binary.parent).replace("'", "''")
result = json.loads(powershell(f"""$s=New-CimInstance -CimClass (Get-CimClass Win32_ProcessStartup) -Property @{{ShowWindow=[uint16]0}} -ClientOnly
$r=Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{{CommandLine='{line}';CurrentDirectory='{working}';ProcessStartupInformation=$s}}
$r | Select-Object ProcessId,ReturnValue | ConvertTo-Json -Compress
"""))
assert result['ReturnValue'] == 0
deadline = time.monotonic() + 5
while not user32.IsWindowVisible(window) and time.monotonic() < deadline:
    time.sleep(0.1)
assert user32.IsWindowVisible(window), 'Second launch should reveal existing window'
assert psutil.Process(pid.value).create_time() == created
deadline = time.monotonic() + 5
while psutil.pid_exists(result['ProcessId']) and time.monotonic() < deadline:
    time.sleep(0.1)
assert not psutil.pid_exists(result['ProcessId']), 'Single instance should terminate second process'
user32.PostMessageW(window, 0x0010, 0, 0)
print('DESKTOP PASS: native WebView window, close hides to tray, engine stays healthy, second launch restores original single instance', flush=True)
