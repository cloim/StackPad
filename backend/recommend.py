"""Suggest unregistered Python and Node servers running from the configured project folders."""
import os
import re
import subprocess
from pathlib import Path

import psutil

# Users choose their project folders on first run; nothing is scanned until then.
DEFAULT_ROOTS = []
TARGETS = {'python.exe', 'pythonw.exe', 'node.exe'}


def under(path, root):
    path, root = os.path.normcase(path), os.path.normcase(root).rstrip('\\/')
    return path == root or path.startswith(root + os.sep)


def mentions(text, root):
    return re.search(re.escape(os.path.normcase(root).rstrip('\\/')) + r'(?=[\\"\'\s;]|$)', os.path.normcase(text)) is not None


def rejoin(args):
    """A single argument was the quoted inner command; several arguments need quotes where they contain spaces."""
    if len(args) == 1:
        return args[0].strip()
    return ' '.join(f'"{a}"' if (' ' in a or '\t' in a) and not a.startswith('"') else a for a in args).strip()


def command_of(process):
    """Return the command a pad can run again: the shell's inner command, or the process command line."""
    args = process.cmdline()
    lowered = [a.lower() for a in args]
    name = process.name().lower()
    if name == 'cmd.exe' and '/c' in lowered:
        return rejoin(args[lowered.index('/c') + 1:])
    if name in ('pwsh.exe', 'powershell.exe') and '-command' in lowered:
        return rejoin(args[lowered.index('-command') + 1:])
    if name == 'node.exe' and len(args) > 1:
        script = Path(args[1]).name.lower()
        if script in ('npm-cli.js', 'npx-cli.js'):
            return subprocess.list2cmdline([script[:3], *args[2:]])
    return subprocess.list2cmdline(args)


def display_name(cwd, roots):
    for root in roots:
        if under(cwd, root):
            parts = Path(cwd).relative_to(Path(root)).parts
            return ' '.join(parts)[:40] or Path(cwd).name or 'Service'
    return Path(cwd).name[:40] or 'Service'


def candidate_key(cwd, command):
    return f'{os.path.normcase(cwd)}|{command}'


def scan(engine):
    """List listening Python/Node process trees under the scan roots that no pad covers."""
    from engine import RUNTIMES, LAUNCHERS, launcher_only
    with engine.lock:
        settings = engine.config.get('recommend', {})
        roots = settings.get('roots') or DEFAULT_ROOTS
        hidden = {entry['key'] for entry in hidden_entries(engine.config)}
        registered_ports = {s['port'] for s in engine.config['services'] if s.get('port')}
        owned = engine.owned_pids()
    ports = {}
    for port, pids in engine.listeners().items():
        for pid in pids:
            ports.setdefault(pid, set()).add(port)
    protected = {os.getpid()}
    try:
        protected |= {p.pid for p in psutil.Process().parents()}
    except psutil.Error:
        pass
    found = {}
    for pid, pid_ports in ports.items():
        if pid in owned or pid in protected or pid_ports & registered_ports:
            continue
        try:
            listener = psutil.Process(pid)
            if listener.name().lower() not in TARGETS:
                continue
            cwd = listener.cwd()
            if not any(under(cwd, r) or mentions(' '.join(listener.cmdline()), r) for r in roots):
                continue
            top = listener
            parent = listener.parent()
            while parent and parent.name().lower() in RUNTIMES | LAUNCHERS and parent.pid not in protected:
                if parent.name().lower() in LAUNCHERS and not launcher_only(parent):
                    break
                try:
                    related = any(under(parent.cwd(), r) or mentions(' '.join(parent.cmdline()), r) for r in roots)
                except psutil.AccessDenied:
                    related = False
                if not related:
                    break
                top = parent
                parent = parent.parent()
            if top.pid in owned:
                continue
            command = command_of(top)
            entry = found.setdefault(top.pid, {'pid': top.pid, 'cwd': cwd, 'command': command, 'ports': set()})
            entry['ports'] |= pid_ports
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    result = []
    for entry in found.values():
        key = candidate_key(entry['cwd'], entry['command'])
        if key in hidden:
            continue
        port = min(entry['ports'])
        result.append({'key': key, 'pid': entry['pid'], 'name': display_name(entry['cwd'], roots), 'command': entry['command'], 'cwd': entry['cwd'],
                       'port': port, 'ports': sorted(entry['ports']), 'health_url': ''})
    return {'roots': roots, 'candidates': sorted(result, key=lambda c: (c['cwd'].lower(), c['port']))}


def save_roots(engine, roots):
    cleaned = []
    for value in roots:
        value = value.strip()
        if not value:
            continue
        path = Path(value)
        if not path.is_absolute() or not path.is_dir():
            raise ValueError(f'존재하는 폴더의 전체 경로를 입력해 주세요: {value}')
        resolved = str(path.resolve())
        if os.path.normcase(resolved) not in {os.path.normcase(c) for c in cleaned}:
            cleaned.append(resolved)
    if not cleaned or len(cleaned) > 10:
        raise ValueError('스캔 폴더를 1개 이상 10개 이하로 지정해 주세요.')
    with engine.lock:
        engine.config.setdefault('recommend', {})['roots'] = cleaned
        engine.save()
    return cleaned


def hidden_entries(config):
    """Hidden candidates with display details; entries saved as bare keys keep working."""
    entries = []
    for item in config.get('recommend', {}).get('hidden', []):
        if isinstance(item, str):
            cwd, _, command = item.partition('|')
            item = {'key': item, 'name': Path(cwd).name, 'cwd': cwd, 'command': command}
        entries.append(item)
    return entries


def hide(engine, key, name='', cwd='', command=''):
    if not key or len(key) > 3000:
        raise ValueError('숨길 추천을 확인해 주세요.')
    fallback_cwd, _, fallback_command = key.partition('|')
    entry = {'key': key, 'name': name or Path(cwd or fallback_cwd).name, 'cwd': cwd or fallback_cwd, 'command': command or fallback_command}
    with engine.lock:
        hidden = engine.config.setdefault('recommend', {}).setdefault('hidden', [])
        if key not in {e['key'] for e in hidden_entries(engine.config)}:
            hidden.append(entry)
            engine.save()


def unhide(engine, key):
    with engine.lock:
        settings = engine.config.setdefault('recommend', {})
        remaining = [item for item in settings.get('hidden', []) if (item if isinstance(item, str) else item['key']) != key]
        if len(remaining) == len(settings.get('hidden', [])):
            raise KeyError('숨긴 추천을 찾을 수 없습니다.')
        settings['hidden'] = remaining
        engine.save()


def reset_hidden(engine):
    with engine.lock:
        engine.config.setdefault('recommend', {})['hidden'] = []
        engine.save()
