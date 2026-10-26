"""Remote Linux services run registered commands through the user's OpenSSH client; nothing is installed remotely."""
import ipaddress
import os
import re
import shutil
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from i18n import system_text
from urllib.parse import urlsplit
from urllib.request import build_opener, ProxyHandler, Request

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# A leading dash would be read as an ssh option, so the destination must start with a letter or digit.
HOST_PATTERN = re.compile(r'^(?:[A-Za-z0-9][A-Za-z0-9._-]*@)?[A-Za-z0-9][A-Za-z0-9._-]*(?::\d{1,5})?$')
SYSTEMD_UNIT = re.compile(r'^[A-Za-z0-9@._:-]+$')
# Prompts for passwords or unknown host keys would stall the engine, so they fail instead.
SSH_OPTIONS = ['-o', 'BatchMode=yes', '-o', 'ConnectTimeout=5', '-o', 'ServerAliveInterval=5', '-o', 'StrictHostKeyChecking=yes']
TIMEOUTS = {'start': 60, 'stop': 60, 'status': 10, 'logs': 15, 'test': 15}
ACTIVE = ('running', 'starting', 'unhealthy')
LOCAL_KEYS = ('command', 'cwd', 'port', 'health_url')
LOG_BYTES = 48_000


def one_line(value):
    value = value.strip()
    if any(c in value for c in ('\x00', '\n', '\r')):
        raise ValueError('한 줄로 입력해 주세요.')
    return value


def ssh_config_path():
    return Path(os.environ.get('STACKPAD_SSH_CONFIG') or Path.home() / '.ssh' / 'config')


def ssh_hosts():
    """Concrete Host aliases from ~/.ssh/config with their HostName, skipping wildcard patterns."""
    try:
        lines = ssh_config_path().read_text('utf-8', errors='replace').splitlines()
    except OSError:
        return []
    hosts, current = [], []
    for line in lines:
        parts = re.split(r'\s*=\s*|\s+', line.strip(), maxsplit=1)
        if len(parts) < 2 or parts[0].startswith('#'):
            continue
        key, value = parts[0].lower(), parts[1].strip().strip('"')
        if key == 'host':
            current = [{'alias': alias, 'hostname': ''} for alias in value.split() if not any(c in alias for c in '*?!')]
            hosts += current
        elif key == 'match':
            current = []
        elif key == 'hostname':
            for host in current:
                host['hostname'] = host['hostname'] or value
    return hosts


def health_host_allowed(hostname, host):
    try:
        address = ipaddress.ip_address(hostname)
        return address.is_private or address.is_loopback
    except ValueError:
        pass
    target = host.rsplit('@', 1)[-1].split(':')[0].lower()
    names = {target, *(h['hostname'].lower() for h in ssh_hosts() if h['alias'].lower() == target and h['hostname'])}
    return hostname.lower() in names


class RemoteSpec(BaseModel):
    model_config = ConfigDict(extra='forbid')
    host: str = Field(min_length=1, max_length=255)
    start: str = Field(min_length=1, max_length=2000)
    stop: str = Field(min_length=1, max_length=2000)
    status: str = Field(min_length=1, max_length=2000)
    logs: str = Field(default='', max_length=2000)
    health_url: str = Field(default='', max_length=1000)

    @field_validator('host', 'start', 'stop', 'status', 'logs', 'health_url')
    @classmethod
    def line(cls, value):
        return one_line(value)

    @field_validator('host')
    @classmethod
    def destination(cls, value):
        if not HOST_PATTERN.match(value):
            raise ValueError('호스트는 SSH 설정의 별칭이나 user@host[:port] 형식으로 입력해 주세요.')
        return value

    @field_validator('start', 'stop', 'status')
    @classmethod
    def required(cls, value):
        if not value:
            raise ValueError('시작, 종료, 상태 명령을 입력해 주세요.')
        return value

    @model_validator(mode='after')
    def health(self):
        if self.health_url:
            url = urlsplit(self.health_url)
            if url.scheme not in ('http', 'https') or not url.hostname or url.username or url.password or not health_host_allowed(url.hostname, self.host):
                raise ValueError('상태 확인 URL은 사설망 주소나 등록한 호스트의 HTTP, HTTPS 주소로 입력해 주세요.')
        return self


def ssh_executable():
    if override := os.environ.get('STACKPAD_SSH'):
        return [override]
    system = Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32' / 'OpenSSH' / 'ssh.exe'
    return [str(system) if system.is_file() else shutil.which('ssh') or str(system)]


def ssh_target(host):
    destination, _, port = host.partition(':')
    return [*(['-p', port] if port else []), destination]


def decode(data):
    return (data or b'').decode('utf-8', errors='replace')


def run_ssh(host, command, timeout):
    """Return {'code', 'output', 'error'}; code is None when ssh did not finish."""
    args = [*ssh_executable(), *SSH_OPTIONS, *ssh_target(host), command]
    try:
        result = subprocess.run(args, stdin=subprocess.DEVNULL, capture_output=True, timeout=timeout, creationflags=0x08000000)
    except subprocess.TimeoutExpired as error:
        return {'code': None, 'output': decode(error.stdout), 'error': f'{timeout}초 안에 응답이 없습니다.'}
    except OSError as error:
        return {'code': None, 'output': '', 'error': f'ssh를 실행하지 못했습니다: {error}'}
    return {'code': result.returncode, 'output': decode(result.stdout), 'error': decode(result.stderr)}


def connection_failed(result):
    return result['code'] is None or result['code'] == 255


def summarize(result, host):
    lines = [line.strip() for line in (result['error'] or result['output']).splitlines() if line.strip()]
    detail = lines[-1][:300] if lines else f"종료 코드 {result['code']}"
    if 'Host key verification failed' in detail or 'No ED25519 host key' in detail or 'host key' in detail.lower() and 'known' in detail.lower():
        return f'{detail}\n터미널에서 ssh {host} 로 한 번 접속해 호스트 키를 등록해 주세요.'
    if 'Permission denied' in detail:
        return f'{detail}\nSSH 키 인증과 ssh-agent 상태를 확인해 주세요.'
    if 'sudo' in detail and 'password' in detail:
        return f'{detail}\n원격 서버의 sudoers에 이 명령을 비밀번호 없이 허용해 주세요.'
    return detail


class RemoteServices:
    """Engine mixin. SSH never runs while the engine lock is held, so slow hosts do not freeze the deck."""

    def remote_init(self):
        self.remote_states = {}
        self.remote_busy = set()
        self.remote_logs = {}
        self.host_limits = {}
        self.remote_pool = ThreadPoolExecutor(4, thread_name_prefix='remote-check')
        self.remote_monitor = threading.Thread(target=self.watch_remote, daemon=True)

    @staticmethod
    def is_remote_service(service):
        return service.get('kind') == 'remote'

    def is_remote(self, service_id):
        with self.lock:
            return self.is_remote_service(self.service(service_id))

    def pad_has_remote(self, pad_id):
        with self.lock:
            group = next((g for g in self.config.get('groups', []) if g['id'] == pad_id), None)
            ids = group['member_ids'] if group else [pad_id]
            return any(self.is_remote_service(s) for s in self.config['services'] if s['id'] in ids)

    def forget_remote(self, service_id):
        with self.lock:
            self.remote_states.pop(service_id, None)
            self.remote_logs.pop(service_id, None)
            hosts = {s.get('remote', {}).get('host') for s in self.config['services'] if self.is_remote_service(s)}
            for host, record in list(self.host_limits.items()):
                if host not in hosts and record['users'] == 0:
                    self.host_limits.pop(host, None)

    def ssh(self, host, command, action):
        with self.lock:
            record = self.host_limits.setdefault(host, {'semaphore': threading.BoundedSemaphore(2), 'users': 0})
            record['users'] += 1
        try:
            with record['semaphore']:
                return run_ssh(host, command, TIMEOUTS[action])
        finally:
            with self.lock:
                record['users'] -= 1
                hosts = {s.get('remote', {}).get('host') for s in self.config['services'] if self.is_remote_service(s)}
                if host not in hosts and record['users'] == 0 and self.host_limits.get(host) is record:
                    self.host_limits.pop(host, None)

    def remote_status(self, service_id):
        return self.remote_states.get(service_id, {}).get('status', 'checking')

    def remote_action(self, service_id, action):
        with self.lock:
            self.check_group_busy(service_id)
            service = self.service(service_id)
            status = self.remote_status(service_id)
            if action == 'start' and status == 'running':
                raise ValueError('이미 실행 중인 서비스입니다.')
            if action == 'stop' and status == 'stopped':
                return
            if service_id in self.remote_busy:
                raise ValueError('원격 명령을 처리하고 있습니다. 완료 후 다시 시도해 주세요.')
            self.remote_busy.add(service_id)
            spec = dict(service['remote'])
        try:
            result = self.ssh(spec['host'], spec[action], action)
        finally:
            with self.lock:
                self.remote_busy.discard(service_id)
        failed = result['code'] != 0
        message = summarize(result, spec['host']) if failed else ''
        with self.lock:
            if not any(s['id'] == service_id for s in self.config['services']):
                return
            state = self.remote_states.setdefault(service_id, {})
            state['generation'] = state.get('generation', 0) + 1
            output = (result['output'] + result['error']).strip()
            state['last'] = {'action': action, 'code': result['code'], 'output': output[-2000:], 'at': time.time()}
            state['message'] = message
            # Check right away, then every few seconds while the service settles.
            state['fast_until'] = time.monotonic() + 30
            state['probed'] = None
            self.remote_logs.pop(service_id, None)
            if failed:
                if connection_failed(result):
                    state['status'] = 'unreachable'
            elif action == 'start':
                state.update(status='starting', pending=time.time())
            else:
                state.update(status='stopped', pending=None)
        if failed:
            label = '시작' if action == 'start' else '종료'
            raise ValueError(f"{service['name']}: 원격 {label} 명령이 실패했습니다.\n{message}")

    def probe(self, service_id):
        """Health URL first, then the status command's exit code; SSH failures mean unreachable."""
        try:
            with self.lock:
                service = next((s for s in self.config['services'] if s['id'] == service_id), None)
                if not service or not self.is_remote_service(service):
                    return
                spec = dict(service['remote'])
                generation = self.remote_states.get(service_id, {}).get('generation', 0)
            status, message = None, ''
            if spec['health_url']:
                try:
                    with build_opener(ProxyHandler({})).open(Request(spec['health_url']), timeout=3) as response:
                        status = 'running' if 200 <= response.status < 400 else None
                except Exception:
                    status = None
            if not status:
                result = self.ssh(spec['host'], spec['status'], 'status')
                if connection_failed(result):
                    status, message = 'unreachable', summarize(result, spec['host'])
                else:
                    status = 'running' if result['code'] == 0 else 'stopped'
            with self.lock:
                current = next((s for s in self.config['services'] if s['id'] == service_id), None)
                if not current or current.get('remote') != spec:
                    return
                state = self.remote_states.setdefault(service_id, {})
                # Discard results for settings or a start/stop that changed while the check ran.
                if service_id in self.remote_busy or state.get('generation', 0) != generation:
                    return
                pending = state.get('pending')
                if status == 'running':
                    state['pending'] = None
                elif status == 'stopped' and pending:
                    status = 'starting' if time.time() - pending < 20 else 'unhealthy'
                    if status == 'unhealthy':
                        message = '시작 명령 뒤 실행 상태를 확인하지 못했습니다. 상태 명령과 로그를 확인해 주세요.'
                if status != 'unreachable' and not message and state.get('last', {}).get('code') not in (0, None):
                    message = state.get('message', '')
                state.update(status=status, message=message, checked=time.time())
        finally:
            with self.lock:
                state = self.remote_states.get(service_id)
                if state is not None:
                    state['in_flight'] = False

    def watch_remote(self):
        while True:
            now = time.monotonic()
            with self.lock:
                for service in self.config['services']:
                    if not self.is_remote_service(service) or service['id'] in self.remote_busy:
                        continue
                    state = self.remote_states.setdefault(service['id'], {'status': 'checking'})
                    if state.get('in_flight'):
                        continue
                    interval = 3 if now < state.get('fast_until', 0) else 15
                    if state.get('probed') is None or now - state['probed'] >= interval:
                        state.update(in_flight=True, probed=now)
                        self.remote_pool.submit(self.probe, service['id'])
            if self.closed.wait(1):
                break
        self.remote_pool.shutdown(wait=False, cancel_futures=True)

    def remote_tail(self, service_id):
        with self.lock:
            spec = dict(self.service(service_id)['remote'])
            cached = self.remote_logs.get(service_id)
        if not spec['logs']:
            return '로그 명령이 등록되지 않았습니다. 패드 설정에서 로그 명령을 입력하면 여기에 표시됩니다.'
        # Several open viewers share one SSH call.
        if cached and time.monotonic() - cached[0] < 4:
            return cached[1]
        result = self.ssh(spec['host'], spec['logs'], 'logs')
        text = result['output'][-LOG_BYTES:]
        if result['code'] != 0:
            text += f"\n[{system_text('로그 명령 실패')}] {summarize(result, spec['host'])}"
        with self.lock:
            current = next((s for s in self.config['services'] if s['id'] == service_id), None)
            if current and current.get('remote') == spec:
                self.remote_logs[service_id] = (time.monotonic(), text)
        return text

    def remote_snapshot(self, service):
        state = self.remote_states.get(service['id'], {})
        status = state.get('status', 'checking')
        checked = state.get('checked')
        return {**{k: v for k, v in service.items() if k != 'runtime'}, 'status': status, 'active': status in ACTIVE, 'pid': None, 'external_pid': None, 'uptime': 0,
                'busy': service['id'] in self.remote_busy, 'message': state.get('message', ''), 'checked_ago': int(time.time() - checked) if checked else None, 'last': state.get('last')}

    def test_connection(self, host):
        result = self.ssh(host, 'true', 'test')
        return {'ok': result['code'] == 0, 'message': '접속을 확인했습니다.' if result['code'] == 0 else summarize(result, host)}
