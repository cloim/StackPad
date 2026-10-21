"""Build and release the StackPad Android app (APK) from the local machine.

Environment (falls back to local machine defaults when unset):
  ANDROID_HOME (or ANDROID_SDK_ROOT)  Android SDK folder (default: D:\\AndroidSDK)
  JAVA_HOME                           JDK 21 (default: D:\\Program Files\\JDK\\jdk-21.0.11+10)
  STACKPAD_KEYSTORE                   release keystore (.jks) with the key alias `stackpad`
  STACKPAD_KEYSTORE_PASSWORD          its password

Standard Pipeline:
  [1/5] Web build (npm run build)
  [2/5] Capacitor sync (npx cap sync android)
  [3/5] Android build & sign (gradlew assembleRelease)
  [4/5] Store artifact in release/
  [5/5] GitHub Release upload (gh release create / upload) [when --release is specified]

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
DEFAULT_KEYSTORE = Path(os.environ.get('STACKPAD_KEYSTORE_PATH') or (Path.home() / '.config' / 'backups' / 'stackpad-keys' / 'stackpad-release.jks'))
DEFAULT_KEYSTORE_PASS = Path(os.environ.get('STACKPAD_KEYSTORE_PASS_PATH') or (Path.home() / '.config' / 'backups' / 'stackpad-keys' / 'android-keystore-password.txt'))


def run(command, **options):
    print('RUN', ' '.join(str(part) for part in command[:4]), flush=True)
    subprocess.run([str(part) for part in command], stdin=subprocess.DEVNULL, check=True, **options)


def resolve_environment():
    sdk = os.environ.get('ANDROID_HOME') or os.environ.get('ANDROID_SDK_ROOT')
    if not sdk or not Path(sdk).is_dir():
        default_sdk = Path(r'D:\AndroidSDK')
        if default_sdk.is_dir():
            sdk = str(default_sdk)
        else:
            raise SystemExit('Android SDK folder not found. Please set ANDROID_HOME.')

    jdk = os.environ.get('JAVA_HOME')
    if not jdk or not Path(jdk).is_dir():
        default_jdk = Path(r'D:\Program Files\JDK\jdk-21.0.11+10')
        if default_jdk.is_dir():
            jdk = str(default_jdk)
        else:
            raise SystemExit('JDK folder not found. Please set JAVA_HOME.')

    keystore = os.environ.get('STACKPAD_KEYSTORE')
    password = os.environ.get('STACKPAD_KEYSTORE_PASSWORD')
    if not (keystore and password):
        if DEFAULT_KEYSTORE.is_file() and DEFAULT_KEYSTORE_PASS.is_file():
            keystore = str(DEFAULT_KEYSTORE)
            password = DEFAULT_KEYSTORE_PASS.read_text('utf-8').strip()

    env = {
        **os.environ,
        'ANDROID_HOME': sdk,
        'ANDROID_SDK_ROOT': sdk,
        'JAVA_HOME': jdk,
    }
    if keystore and password:
        env['STACKPAD_KEYSTORE'] = keystore
        env['STACKPAD_KEYSTORE_PASSWORD'] = password

    return env, sdk, bool(keystore and password)


def sync_version():
    # versionCode must grow with every release for Android to accept the update: 1.2.3 becomes 10203.
    version = json.loads((ROOT / 'package.json').read_text('utf-8'))['version']
    parts = [int(p) for p in re.findall(r'\d+', version)[:3]]
    major = parts[0] if len(parts) > 0 else 1
    minor = parts[1] if len(parts) > 1 else 0
    patch = parts[2] if len(parts) > 2 else 0

    code = major * 10000 + minor * 100 + patch
    text = GRADLE.read_text('utf-8')
    text = re.sub(r'versionCode \d+', f'versionCode {code}', text)
    text = re.sub(r'versionName "[^"]+"', f'versionName "{version}"', text)
    GRADLE.write_text(text, 'utf-8')
    return version


def upload_to_github(version, artifact_path):
    tag = f'v{version}'
    print(f'[5/5] GitHub Release Upload: {tag} ({artifact_path})', flush=True)

    # Check if release already exists
    check = subprocess.run(['gh', 'release', 'view', tag], stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding='utf-8')
    if check.returncode == 0:
        print(f'Existing release found for {tag}. Uploading asset...', flush=True)
        run(['gh', 'release', 'upload', tag, str(artifact_path), '--clobber'])
    else:
        print(f'Creating new release {tag}...', flush=True)
        run([
            'gh', 'release', 'create', tag, str(artifact_path),
            '--title', f'StackPad {version}',
            '--generate-notes',
        ])
    print(f'GitHub Release {tag} successfully updated.', flush=True)


def main():
    parser = argparse.ArgumentParser(description='Build and release StackPad Android APK locally.')
    parser.add_argument('--out', default=str(ROOT / 'release/StackPad-Android'), help='folder for StackPad.apk')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--test', action='store_true', help='emulator test build (VITE_ANDROID_TEST=1); never released')
    mode.add_argument('--release', action='store_true', help='upload signed APK to GitHub Release via gh CLI')
    args = parser.parse_args()

    env, sdk, signed = resolve_environment()
    if args.release and not signed:
        raise SystemExit('Cannot release an unsigned APK. Ensure keystore credentials are provided.')

    env.pop('VITE_ANDROID_TEST', None)
    if args.test:
        env['VITE_ANDROID_TEST'] = '1'
        signed = False

    version = sync_version()
    print(f'=== StackPad Android Pipeline v{version} (signed={signed}, release={args.release}) ===', flush=True)

    npm, npx = ('npm.cmd', 'npx.cmd') if os.name == 'nt' else ('npm', 'npx')

    # [1/5] Web Build
    print('[1/5] Web Build (npm run build)...', flush=True)
    run([npm, 'run', 'build'], cwd=ROOT, env=env)

    # [2/5] Capacitor Sync
    print('[2/5] Capacitor Sync (npx cap sync android)...', flush=True)
    run([npx, 'cap', 'sync', 'android'], cwd=ROOT, env=env)

    # [3/5] Android Gradle Build & apksigner
    gradlew = ANDROID / ('gradlew.bat' if os.name == 'nt' else 'gradlew')
    task = 'assembleRelease' if signed else 'assembleDebug'
    print(f'[3/5] Android Build ({task})...', flush=True)
    run([gradlew, task, '--no-daemon'], cwd=ANDROID, env=env)

    variant = 'release' if signed else 'debug'
    apk = ANDROID / f'app/build/outputs/apk/{variant}/app-{variant}.apk'
    if signed:
        build_tools = sorted((Path(sdk) / 'build-tools').glob('*/apksigner*'))
        if build_tools:
            print('Verifying APK signature...', flush=True)
            run([build_tools[-1], 'verify', '--print-certs', apk], env=env)

    # [4/5] Store Artifact
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    target = out / ('StackPad.apk' if signed else 'StackPad-debug.apk')
    shutil.copy2(apk, target)
    print(f'[4/5] APK stored in: {target}', flush=True)

    # [5/5] GitHub Release Upload
    if args.release:
        upload_to_github(version, target)
    else:
        print('[5/5] Skipped GitHub Release upload (use --release to upload).', flush=True)

    print(f'Pipeline completed successfully: {target}', flush=True)


if __name__ == '__main__':
    main()
