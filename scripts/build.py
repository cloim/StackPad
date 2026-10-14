"""Build StackPad for Windows: the web screen, the engine and the desktop app.

Default: a portable folder (StackPad.exe, StackPadEngine.exe, a `portable` marker) plus its zip.
--installer: also the NSIS installer and the signed updater files; needs TAURI_SIGNING_PRIVATE_KEY in the environment.
Run inside a WMI worker on a desktop PC.
"""
import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
from PIL import Image, ImageDraw

root = Path(__file__).resolve().parents[1]
os.chdir(root)
parser = argparse.ArgumentParser()
parser.add_argument('--release-dir', default=str(root / 'release/StackPad'))
parser.add_argument('--installer', action='store_true', help='also build the NSIS installer and updater artifacts')
args = parser.parse_args()
npm = 'npm.cmd' if os.name == 'nt' else 'npm'


def run(command):
    print('BUILD', command, flush=True)
    subprocess.run(command, stdin=subprocess.DEVNULL, check=True)


icons = root / 'src-tauri/icons'
icons.mkdir(parents=True, exist_ok=True)
image = Image.new('RGBA', (256, 256), '#24282a')
draw = ImageDraw.Draw(image)
for x, y, color in [(39, 39, '#efa668'), (139, 39, '#cf8c54'), (39, 139, '#876347'), (139, 139, '#efa668')]:
    draw.rounded_rectangle((x, y, x + 78, y + 78), radius=15, fill=color)
image.save(icons / 'icon.png')
image.save(icons / 'icon.ico', sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
run([npm, 'run', 'build'])
run([sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--onefile', '--windowed', '--name', 'StackPadEngine-x86_64-pc-windows-msvc',
     '--distpath', 'src-tauri/binaries', '--workpath', 'build/engine', '--add-data', 'dist;dist', '--paths', 'backend',
     '--collect-all', 'uvicorn', '--collect-all', 'jwt', '--hidden-import', 'psutil', 'backend/main.py'])
run([npm, 'run', 'desktop:build' if not args.installer else 'desktop:installer'])

target = root / 'src-tauri/target/release'
desktop = next(path for path in (target / 'StackPad.exe', target / 'stackpad.exe') if path.is_file())
release = Path(args.release_dir).resolve()
release.mkdir(parents=True, exist_ok=True)
shutil.copy2(desktop, release / 'StackPad.exe')
shutil.copy2(root / 'src-tauri/binaries/StackPadEngine-x86_64-pc-windows-msvc.exe', release / 'StackPadEngine.exe')
shutil.copy2(root / 'README.md', release / 'README.md')
shutil.copy2(root / 'LICENSE', release / 'LICENSE')
# The desktop app offers a download link instead of installing updates over a portable copy.
(release / 'portable').write_text('This copy of StackPad was unpacked from the portable zip.\n', 'utf-8')
shutil.make_archive(str(release.parent / 'StackPad-Windows-x64-portable'), 'zip', release)
if args.installer:
    bundle = target / 'bundle/nsis'
    for artifact in bundle.glob('StackPad_*'):
        shutil.copy2(artifact, release.parent / artifact.name)
print('BUILD COMPLETE:', release, flush=True)
