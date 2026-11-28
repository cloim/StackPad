"""Expose the engine to the user's tailnet with `tailscale serve`, leaving other serve entries untouched."""
import json
import os
import re
import shutil
import subprocess
import threading
from pathlib import Path
from urllib.parse import urlsplit

PREFERRED_PORTS = (443, 48731, 48732, 48733, 48734)
# Pairing and the background watcher may both try to add the serve entry.
_serve_lock = threading.Lock()


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
    try:
        result = subprocess.run([binary, *arguments], stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding='utf-8',
                                errors='replace', timeout=timeout, creationflags=0x08000000)
    except subprocess.TimeoutExpired:
        raise RuntimeError('Tailscale이 응답하지 않습니다.') from None
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout).strip() or 'Tailscale 명령을 실행하지 못했습니다.')
    return result.stdout


def _external_url(host, port):
    return f'https://{host}' if port == 443 else f'https://{host}:{port}'


def _engine_targets(engine_port):
    return {f'http://127.0.0.1:{engine_port}', f'http://localhost:{engine_port}', f'127.0.0.1:{engine_port}', f'localhost:{engine_port}'}


def find_serve(serve, host, engine_port):
    """Return the existing serve URL that proxies to the engine, and the HTTPS ports already taken."""
    targets = _engine_targets(engine_port)
    used = {int(port) for port in (serve.get('TCP') or {})}
    for address, web in (serve.get('Web') or {}).items():
        name, _, port = address.rpartition(':')
        handler = (web.get('Handlers') or {}).get('/') or {}
        if name == host and handler.get('Proxy', '').rstrip('/') in targets:
            return _external_url(host, int(port)), used
    return None, used


def saved_serve(serve, host, port, engine_port):
    """'engine' when host:port already proxies to the engine, 'other' when something else holds that port, else None."""
    web = (serve.get('Web') or {}).get(f'{host}:{port}')
    if web is not None:
        handler = (web.get('Handlers') or {}).get('/') or {}
        return 'engine' if handler.get('Proxy', '').rstrip('/') in _engine_targets(engine_port) else 'other'
    return 'other' if str(port) in (serve.get('TCP') or {}) else None


def restore(engine_port, saved_url):
    """Put the saved external address back on `tailscale serve` when it is missing, e.g. after Tailscale was reinstalled.

    Paired phones remember this exact address, so it is restored as is rather than moved to another port.
    Returns True when the entry was added again, False when it was already there, and raises when it cannot be restored.
    """
    if not saved_url:
        return False
    parts = urlsplit(saved_url)
    port = parts.port or 443
    with _serve_lock:
        if not executable():
            raise RuntimeError('Tailscale을 설치해 주세요.')
        state = json.loads(_run('status', '--json'))
        host = (state.get('Self') or {}).get('DNSName', '').rstrip('.')
        if state.get('BackendState') != 'Running' or not host:
            raise RuntimeError('Tailscale에 로그인하고 연결해 주세요.')
        if host.lower() != (parts.hostname or '').lower():
            raise RuntimeError('Tailscale 주소가 바뀌었습니다. 외부 주소를 다시 연결해 주세요.')
        current = saved_serve(json.loads(_run('serve', 'status', '--json') or '{}'), host, port, engine_port)
        if current == 'engine':
            return False
        if current == 'other':
            raise RuntimeError('저장된 외부 주소의 포트를 다른 Tailscale 서비스가 쓰고 있습니다.')
        _run('serve', '--bg', f'--https={port}', f'http://127.0.0.1:{engine_port}', timeout=60)
        return True


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
    with _serve_lock:
        return _connect(engine_port)


def _connect(engine_port):
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


SERVE_COMMAND = re.compile(r'tailscale(?:\.exe)?"?\s+serve\s+(?P<arguments>.*)$', re.IGNORECASE)
LOOPBACK = ('127.0.0.1', 'localhost')


def serve_target(command):
    """(HTTPS port, local port) when a pad component runs `tailscale serve --https=P http://127.0.0.1:L`, else None."""
    match = SERVE_COMMAND.search(command or '')
    if not match:
        return None
    arguments = match['arguments'].replace('"', ' ').split()
    if 'off' in arguments or 'reset' in arguments or 'status' in arguments:
        return None
    https, local = 443, None
    for index, argument in enumerate(arguments):
        if argument.startswith('--https='):
            value = argument.partition('=')[2]
        elif argument == '--https' and index + 1 < len(arguments):
            value = arguments[index + 1]
        else:
            value = None
            if argument.isdigit():
                local = int(argument)
            elif not argument.startswith('-'):
                parts = urlsplit(argument if '://' in argument else f'http://{argument}')
                try:
                    if parts.hostname in LOOPBACK and parts.port:
                        local = parts.port
                except ValueError:
                    pass
        if value is not None:
            if not value.isdigit():
                return None
            https = int(value)
    return (https, local) if local else None


def host():
    """This PC's tailnet name while Tailscale is connected, else None."""
    if not executable():
        return None
    state = json.loads(_run('status', '--json'))
    name = (state.get('Self') or {}).get('DNSName', '').rstrip('.')
    return name if state.get('BackendState') == 'Running' and name else None


def external_url(name, port):
    return _external_url(name, port)


def _all_web(serve):
    """Background and foreground `serve` entries; a pad's own `tailscale serve` component shows up as foreground."""
    web = dict(serve.get('Web') or {})
    tcp = set(serve.get('TCP') or {})
    for session in (serve.get('Foreground') or {}).values():
        web.update(session.get('Web') or {})
        tcp.update(session.get('TCP') or {})
    return web, tcp


def serve_local_ports(name, ports):
    """Proxy https://<name>:<port> to the same local port for each port, adding the missing background entries.

    Returns the ports that now reach their local server; a port another service holds is left out.
    """
    with _serve_lock:
        web, tcp = _all_web(json.loads(_run('serve', 'status', '--json') or '{}'))
        ready = set()
        for port in sorted(set(ports)):
            entry = web.get(f'{name}:{port}')
            if entry is not None:
                target = ((entry.get('Handlers') or {}).get('/') or {}).get('Proxy', '').rstrip('/')
                if target in _engine_targets(port):
                    ready.add(port)
                continue
            if str(port) in tcp:
                continue
            _run('serve', '--bg', f'--https={port}', f'http://127.0.0.1:{port}', timeout=60)
            ready.add(port)
        return ready


def same_origin(url, scheme, host):
    """True when a request's scheme and Host header belong to the saved external address."""
    if not url:
        return False
    parts = urlsplit(url)
    return parts.scheme == scheme and parts.netloc.lower() == (host or '').lower()
