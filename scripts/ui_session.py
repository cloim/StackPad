"""Seed an isolated test engine's data folder with a signed-in owner, so UI tests skip Google sign-in.

Usage: python scripts/ui_session.py <data-dir> [token]
Browsers then send the cookie `stackpad_session=<token>` (default: stackpad-ui-test-session).
"""
import hashlib
import json
import sys
import time
from pathlib import Path

DEFAULT_TOKEN = 'stackpad-ui-test-session'
OWNER = 'owner@example.com'


def seed(data_dir, token=DEFAULT_TOKEN):
    data = Path(data_dir)
    data.mkdir(parents=True, exist_ok=True)
    config_path = data / 'config.json'
    config = json.loads(config_path.read_text('utf-8')) if config_path.exists() else {'services': []}
    config['auth'] = {'client_id': 'ui-test.apps.googleusercontent.com', 'client_secret': 'ui-test', 'owner': OWNER, 'allowed': [OWNER]}
    config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), 'utf-8')
    sessions_path = data / 'sessions.json'
    sessions = json.loads(sessions_path.read_text('utf-8')) if sessions_path.exists() else {}
    sessions[hashlib.sha256(token.encode()).hexdigest()] = {'expires': time.time() + 86400, 'email': OWNER, 'kind': 'browser', 'name': '', 'created': time.time()}
    sessions_path.write_text(json.dumps(sessions), 'utf-8')
    return token


if __name__ == '__main__':
    print(seed(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else DEFAULT_TOKEN))
