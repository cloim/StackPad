"""Run the isolated development engine with browser sessions checked by the installed engine."""
import re
import sys
from pathlib import Path

import httpx
import uvicorn

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from main import create_app


def installed_session(client, credential):
    if not credential or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', credential):
        return None
    try:
        response = client.get('/api/auth', headers={'Cookie': f'stackpad_session={credential}'})
        response.raise_for_status()
        state = response.json()
    except (httpx.HTTPError, ValueError):
        return None
    if isinstance(state, dict) and state.get('authenticated') is True and isinstance(state.get('email'), str):
        return {'email': state['email']}
    return None


if __name__ == '__main__':
    data_dir = Path.home() / '.config' / 'stackpad-dev'
    with httpx.Client(base_url='http://127.0.0.1:48731', timeout=2, trust_env=False) as installed:
        app = create_app(data_dir, ROOT / 'dist', session_lookup=lambda credential: installed_session(installed, credential))
        uvicorn.run(app, host='127.0.0.1', port=48732, proxy_headers=True, forwarded_allow_ips='127.0.0.1')
