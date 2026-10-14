"""Build the StackPad Android app (APK) from the web screen.

Environment:
  ANDROID_HOME (or ANDROID_SDK_ROOT)  Android SDK folder
  JAVA_HOME                           JDK 21
  STACKPAD_KEYSTORE                   release keystore (.jks) with the key alias `stackpad`
  STACKPAD_KEYSTORE_PASSWORD          its password; without both, a debug APK is built

The version comes from package.json, so desktop and Android releases share one number.
Run inside a WMI worker; the Gradle build takes several minutes.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ANDROID = ROOT / 'android'
GRADLE = ANDROID / 'app/build.gradle'


def run(command, **options):
    print('RUN', ' '.join(str(part) for part in command[:4]), flush=True)
    subprocess.run([str(part) for part in command], stdin=subprocess.DEVNULL, check=True, **options)


def sync_version():
    # versionCode must grow with every release for Android to accept the update: 1.2.3 becomes 10203.
    version = json.loads((ROOT / 'package.json').read_text('utf-8'))['version']
    major, minor, patch = (int(part) for part in version.split('.')[:3])
    text = GRADLE.read_text('utf-8')
    text = re.sub(r'versionCode \d+', f'versionCode {major * 10000 + minor * 100 + patch}', text)
    text = re.sub(r'versionName "[^"]+"', f'versionName "{version}"', text)
    GRADLE.write_text(text, 'utf-8')
    return version


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', default=str(ROOT / 'release/StackPad-Android'), help='folder for StackPad.apk')
    parser.add_argument('--test', action='store_true', help='emulator test build that may pair with http://localhost through adb reverse; never released')
    args = parser.parse_args()
    sdk = os.environ.get('ANDROID_HOME') or os.environ.get('ANDROID_SDK_ROOT')
    if not sdk or not Path(sdk).is_dir():
        raise SystemExit('Set ANDROID_HOME to the Android SDK folder.')
    if not os.environ.get('JAVA_HOME'):
        raise SystemExit('Set JAVA_HOME to a JDK 21 folder.')
    signed = bool(os.environ.get('STACKPAD_KEYSTORE') and os.environ.get('STACKPAD_KEYSTORE_PASSWORD'))
    env = {**os.environ, 'ANDROID_HOME': sdk, 'ANDROID_SDK_ROOT': sdk}
    env.pop('VITE_ANDROID_TEST', None)
    if args.test:
        env['VITE_ANDROID_TEST'] = '1'
    version = sync_version()
    npm, npx = ('npm.cmd', 'npx.cmd') if os.name == 'nt' else ('npm', 'npx')
    run([npm, 'run', 'build'], cwd=ROOT, env=env)
    run([npx, 'cap', 'sync', 'android'], cwd=ROOT, env=env)
    gradlew = ANDROID / ('gradlew.bat' if os.name == 'nt' else 'gradlew')
    task = 'assembleRelease' if signed else 'assembleDebug'
    run([gradlew, task, '--no-daemon'], cwd=ANDROID, env=env)
    variant = 'release' if signed else 'debug'
    apk = ANDROID / f'app/build/outputs/apk/{variant}/app-{variant}.apk'
    if signed:
        build_tools = sorted((Path(sdk) / 'build-tools').glob('*/apksigner*'))
        if build_tools:
            run([build_tools[-1], 'verify', '--print-certs', apk], env=env)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    target = out / ('StackPad.apk' if signed else 'StackPad-debug.apk')
    shutil.copy2(apk, target)
    print(f'APK {version} ({variant}): {target}', flush=True)


if __name__ == '__main__':
    main()
