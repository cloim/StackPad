"""Expose the engine to the user's tailnet with `tailscale serve`, leaving other serve entries untouched."""
import json
import os
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlsplit

PREFERRED_PORTS = (443, 48731, 48732, 48733, 48734)


def executable():
    found = shutil.which('tailscale')
    if found:
        return found
    default = Path(os.environ.get('ProgramFiles', r'C:\Program Files')) / 'Tailscale' / 'tailscale.exe'
    return str(default) if default.is_file() else None


def _run(*arguments, timeout=20):
    binary = executable()
    if not binary:
        raise RuntimeError('Tailscale을 설치해 주세요.')
    result = subprocess.run([binary, *arguments], stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding='utf-8',
                            errors='replace', timeout=timeout, creationflags=0x08000000)
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout).strip() or 'Tailscale 명령을 실행하지 못했습니다.')
    return result.stdout


def _external_url(host, port):
    return f'https://{host}' if port == 443 else f'https://{host}:{port}'


def find_serve(serve, host, engine_port):
    """Return the existing serve URL that proxies to the engine, and the HTTPS ports already taken."""
    targets = {f'http://127.0.0.1:{engine_port}', f'http://localhost:{engine_port}', f'127.0.0.1:{engine_port}', f'localhost:{engine_port}'}
    used = {int(port) for port in (serve.get('TCP') or {})}
    for address, web in (serve.get('Web') or {}).items():
        name, _, port = address.rpartition(':')
        handler = (web.get('Handlers') or {}).get('/') or {}
        if name == host and handler.get('Proxy', '').rstrip('/') in targets:
            return _external_url(host, int(port)), used
    return None, used


def status(engine_port):
    if not executable():
        return {'installed': False, 'running': False, 'host': None, 'url': None}
    state = json.loads(_run('status', '--json'))
    host = (state.get('Self') or {}).get('DNSName', '').rstrip('.') or None
    running = state.get('BackendState') == 'Running' and bool(host)
    url = None
    if running:
        url, _ = find_serve(json.loads(_run('serve', 'status', '--json') or '{}'), host, engine_port)
    return {'installed': True, 'running': running, 'host': host, 'url': url}


def connect(engine_port):
    current = status(engine_port)
    if not current['installed']:
        raise RuntimeError('Tailscale을 설치해 주세요.')
    if not current['running']:
        raise RuntimeError('Tailscale에 로그인하고 연결해 주세요.')
    if current['url']:
        return current['url']
    _, used = find_serve(json.loads(_run('serve', 'status', '--json') or '{}'), current['host'], engine_port)
    port = next((port for port in PREFERRED_PORTS if port not in used), None)
    if port is None:
        raise RuntimeError('비어 있는 Tailscale HTTPS 포트를 찾지 못했습니다.')
    _run('serve', '--bg', f'--https={port}', f'http://127.0.0.1:{engine_port}', timeout=60)
    return _external_url(current['host'], port)


def same_origin(url, scheme, host):
    """True when a request's scheme and Host header belong to the saved external address."""
    if not url:
        return False
    parts = urlsplit(url)
    return parts.scheme == scheme and parts.netloc.lower() == (host or '').lower()
