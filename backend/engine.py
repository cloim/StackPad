"""Owned-process service supervisor. Windows launches are detached through WMI."""
import base64
from concurrent.futures import ThreadPoolExecutor
from collections import deque
import hashlib
import json
import logging
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from events import EventHub

from i18n import system_text
from typing import Annotated, Literal, Union
from urllib.parse import urlsplit
from urllib.request import build_opener, ProxyHandler, Request

import psutil
from pydantic import BaseModel, Discriminator, Field, Tag, field_validator, ConfigDict
from groups import GroupManager, PAD_COLORS, nearest_color
from padsets import Padsets
from docker_services import DockerServices, DockerServiceInput, docker_cli, container_name
from remote import LOCAL_KEYS, RemoteServices, RemoteSpec
from scenes import SceneManager, SceneInput
from schedules import ScheduleManager, ScheduleInput


def pad_color(value):
    if value not in PAD_COLORS:
        raise ValueError('제공된 패드 색상을 선택해 주세요.')
    return value


class ServiceInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    kind: Literal['local'] = 'local'
    name: str = Field(min_length=1, max_length=40)
    command: str = Field(min_length=1, max_length=2000)
    cwd: str = Field(min_length=1, max_length=500)
    port: int | None = Field(default=None, ge=1, le=65535)
    health_url: str = Field(default='', max_length=1000)
    color: str = '#22c55e'
    autostart: bool = False
    slot: int = Field(ge=0, le=15)
    padset_id: str = 'default'
    restart_policy: Literal['never', 'on-failure'] = 'never'
    restart_max: int = Field(default=3, ge=1, le=10)

    @field_validator('name', 'command', 'cwd')
    @classmethod
    def clean(cls, value):
        value = value.strip()
        if not value or any(c in value for c in ('\x00', '\n', '\r')):
            raise ValueError('한 줄로 입력해 주세요.')
        return value

    @field_validator('cwd')
    @classmethod
    def directory(cls, value):
        if not Path(value).is_dir() or not Path(value).is_absolute():
            raise ValueError('존재하는 폴더의 전체 경로를 입력해 주세요.')
        return str(Path(value).resolve())

    @field_validator('health_url')
    @classmethod
    def local_health(cls, value):
        if value:
            url = urlsplit(value)
            if url.scheme not in ('http', 'https') or url.hostname not in ('127.0.0.1', 'localhost', '::1') or url.username or url.password:
                raise ValueError('상태 확인 URL은 로컬 HTTP 또는 HTTPS 주소로 입력해 주세요.')
        return value

    @field_validator('color')
    @classmethod
    def valid_color(cls, value):
        return pad_color(value)


class RemoteServiceInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    kind: Literal['remote'] = 'remote'
    name: str = Field(min_length=1, max_length=40)
    remote: RemoteSpec
    color: str = '#22c55e'
    # Remote services are managed on their server, so they never start with Windows.
    autostart: Literal[False] = False
    slot: int = Field(ge=0, le=15)
    padset_id: str = 'default'

    @field_validator('name')
    @classmethod
    def clean(cls, value):
        value = value.strip()
        if not value or any(c in value for c in ('\x00', '\n', '\r')):
            raise ValueError('한 줄로 입력해 주세요.')
        return value

    @field_validator('color')
    @classmethod
    def valid_color(cls, value):
        return pad_color(value)


def service_kind(value):
    return (value.get('kind') if isinstance(value, dict) else getattr(value, 'kind', None)) or 'local'


AnyServiceInput = Annotated[Union[Annotated[ServiceInput, Tag('local')], Annotated[RemoteServiceInput, Tag('remote')], Annotated[DockerServiceInput, Tag('docker')]], Discriminator(service_kind)]


def replace_kind(service, data):
    """Drop the other kind's settings when a service switches between local and remote."""
    for key in (*LOCAL_KEYS, 'remote', 'container'):
        service.pop(key, None)
    service.update(data)


# External launches are traced only through these processes, never through IDE or terminal hosts.
RUNTIMES = {'python.exe', 'pythonw.exe', 'uv.exe', 'uvx.exe', 'node.exe', 'bun.exe', 'deno.exe', 'java.exe', 'javaw.exe', 'dotnet.exe'}
LAUNCHERS = {'cmd.exe', 'pwsh.exe', 'powershell.exe'}


def launcher_only(process):
    """Shells running a single command are part of the server; interactive shells are not."""
    args = [a.lower() for a in process.cmdline()[1:]]
    if any(a in ('-noexit', '-noe', '/k') for a in args):
        return False
    return any(a in ('/c', '-c', '-command', '-file', '-f', '-encodedcommand', '-ec') for a in args)


def with_error_line(message, line):
    # Clients show pad_name as the title; the log line goes on its own line so the message still translates.
    return f'{message}\n{line}' if line else message


def port_open(port):
    # Servers bound to localhost may listen on IPv6 only.
    for family, host in ((socket.AF_INET, '127.0.0.1'), (socket.AF_INET6, '::1')):
        try:
            with socket.socket(family) as probe:
                probe.settimeout(0.3)
                if probe.connect_ex((host, port)) == 0:
                    return True
        except OSError:
            continue
    return False


def powershell(script):
    encoded = base64.b64encode(script.encode('utf-16-le')).decode('ascii')
    result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-EncodedCommand', encoded], stdin=subprocess.DEVNULL, capture_output=True, timeout=20, creationflags=0x08000000)
    if result.returncode:
        raise RuntimeError(result.stderr.decode('utf-8', errors='replace')[-800:])
    return result.stdout.decode('utf-8-sig', errors='replace').strip()


def vscode_path():
    # Launch Code.exe itself: the code.cmd shim on PATH would flash a console window.
    candidates = []
    if shim := shutil.which('code'):
        candidates.append(Path(shim).resolve().parent.parent / 'Code.exe')
    for variable, folder in (('LOCALAPPDATA', 'Programs/Microsoft VS Code'), ('ProgramFiles', 'Microsoft VS Code'), ('ProgramFiles(x86)', 'Microsoft VS Code')):
        if base := os.environ.get(variable):
            candidates.append(Path(base) / folder / 'Code.exe')
    return next((str(path) for path in candidates if path.is_file()), None)


class Engine(GroupManager, RemoteServices, Padsets, DockerServices, SceneManager, ScheduleManager):
    def __init__(self, data_dir, desktop_exe=None):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.logs = self.data_dir / 'logs'
        self.logs.mkdir(exist_ok=True)
        self.path = self.data_dir / 'config.json'
        self.lock = threading.RLock()
        self.events = EventHub()
        self.wake = threading.Event()
        self.stats = {'listener_calls': 0, 'ticks': 0}
        self.last_services_poll = 0
        self.last_activity = time.time()
        self._last_services_hash = None
        self.docker_busy = set()
        self.desktop_exe = desktop_exe
        self.samples = {}
        self.externals = {}
        self.git_states = {}
        self.last_git_check = 0
        self.git_futures = {}
        self.git_pool = ThreadPoolExecutor(4, thread_name_prefix='git-status')
        self.group_operations = {}
        self.restarts = {}
        self.alerts = deque(maxlen=100)
        self._alert_counter = 0
        self._last_unhealthy = set()
        self.group_progress = {}
        self.scene_progress = {}
        self.scene_threads = {}
        self.schedule_last_run = {}
        self.scheduler_thread = None
        self.history = {}
        self.last_history_tick = 0
        self.closed = threading.Event()
        self.config = json.loads(self.path.read_text('utf-8')) if self.path.exists() else {'services': []}
        # Google sign-in replaced the former app password.
        if self.config.pop('password', None) is not None:
            self.save()
        # Pads saved with an earlier palette keep a similar color from the current one.
        pads = [*self.config['services'], *self.config.get('groups', [])]
        if any(p.get('color') not in PAD_COLORS for p in pads):
            for pad in pads:
                pad['color'] = nearest_color(pad.get('color', PAD_COLORS[0]))
            self.save()
        self.init_padsets()
        self.config.setdefault('log_retention_days', 14)
        # Existing setups already chose their folders, so the first-run folder prompt is only for new installs.
        if 'onboarding_done' not in self.config and (self.config['services'] or self.config.get('recommend', {}).get('roots')):
            self.config['onboarding_done'] = True
        # AI usage reads unofficial CLI endpoints, so new installs start with it off; existing setups keep it on.
        if 'usage_providers' not in self.config:
            self.config['usage_providers'] = ['claude', 'codex', 'antigravity'] if self.config['services'] else []
        self.migrate_legacy_files()
        self.purge_expired_logs()
        self.start_scheduler()
        self.monitor = threading.Thread(target=self.watch, daemon=True)
        self.remote_init()

    def service_dir(self, service_id):
        directory = self.data_dir / 'services' / service_id
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    def service_logs_dir(self, service_id):
        directory = self.service_dir(service_id) / 'logs'
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    def current_service_log(self, service_id):
        today = time.strftime('%Y-%m-%d')
        return self.service_logs_dir(service_id) / f'{today}.log'

    def latest_service_log(self, service_id):
        log_dir = self.service_logs_dir(service_id)
        log_files = sorted(log_dir.glob('*.log'), key=lambda p: p.name, reverse=True)
        if log_files:
            return log_files[0]
        legacy = self.logs / f'{service_id}.log'
        if legacy.exists():
            return legacy
        return self.current_service_log(service_id)

    def migrate_legacy_files(self):
        try:
            nested_engine_dir = self.logs / 'engine'
            if nested_engine_dir.is_dir():
                for item in list(nested_engine_dir.iterdir()):
                    target = self.logs / item.name
                    if not target.exists():
                        try:
                            shutil.move(item, target)
                        except Exception:
                            pass
                    else:
                        try:
                            item.unlink()
                        except Exception:
                            pass
                shutil.rmtree(nested_engine_dir, ignore_errors=True)

            if self.logs.exists():
                for item in list(self.logs.glob('*.log')):
                    if item.name.startswith('engine-'):
                        continue
                    if item.name.endswith('.previous.log'):
                        service_id = item.name[:-len('.previous.log')]
                        target_name = 'legacy.previous.log'
                    else:
                        service_id = item.stem
                        target_name = 'legacy.log'
                    if len(service_id) == 32:
                        target_dir = self.service_logs_dir(service_id)
                        target_file = target_dir / target_name
                        if not target_file.exists():
                            try:
                                shutil.copy2(item, target_file)
                            except Exception:
                                pass
                        try:
                            item.unlink()
                        except Exception:
                            pass
            for ext in ('.cmd', '.txt'):
                for item in list(self.data_dir.glob(f'run-*{ext}')):
                    service_id = item.name[4:-len(ext)]
                    if len(service_id) == 32:
                        target_dir = self.service_dir(service_id)
                        target_file = target_dir / f'run{ext}'
                        if not target_file.exists():
                            try:
                                shutil.copy2(item, target_file)
                            except Exception:
                                pass
                        try:
                            item.unlink()
                        except Exception:
                            pass
        except Exception as error:
            logging.warning('Legacy files migration skipped: %s', error)

    def purge_expired_logs(self):
        retention_days = self.config.get('log_retention_days', 14)
        if not retention_days or retention_days <= 0:
            return
        cutoff_date = datetime.now().date() - timedelta(days=retention_days)
        today_date = datetime.now().date()

        services_dir = self.data_dir / 'services'
        if services_dir.exists():
            for s_dir in services_dir.iterdir():
                if not s_dir.is_dir():
                    continue
                logs_dir = s_dir / 'logs'
                if not logs_dir.exists():
                    continue
                for log_file in logs_dir.glob('*.log'):
                    stem = log_file.stem
                    try:
                        file_date = datetime.strptime(stem, '%Y-%m-%d').date()
                        if file_date < cutoff_date and file_date != today_date:
                            try:
                                log_file.unlink()
                            except Exception:
                                pass
                    except ValueError:
                        try:
                            mtime = datetime.fromtimestamp(log_file.stat().st_mtime).date()
                            if mtime < cutoff_date:
                                log_file.unlink()
                        except Exception:
                            pass

        engine_logs_dir = self.logs
        if engine_logs_dir.exists():
            for log_file in engine_logs_dir.glob('engine-*.log'):
                try:
                    date_str = log_file.stem.replace('engine-', '')
                    file_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                    if file_date < cutoff_date and file_date != today_date:
                        try:
                            log_file.unlink()
                        except Exception:
                            pass
                except ValueError:
                    pass

    def services_payload(self):
        with self.lock:
            result = self.snapshot()
            for item in result:
                item.pop('_cpu_time', None)
                item.pop('_sample_time', None)
            return {
                'services': result,
                'groups': self.config.get('groups', []),
                'links': self.pad_links(),
                'padsets': self.config.get('padsets', []),
                'group_progress': dict(getattr(self, 'group_progress', {})),
                'scenes': self.get_scenes(),
                'scene_progress': dict(self.scene_progress),
                'schedules': self.get_schedules(),
            }

    def notify_services(self):
        try:
            payload = self.services_payload()
            digest = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode('utf-8')).hexdigest()
            if digest != getattr(self, '_last_services_hash', None):
                self._last_services_hash = digest
                self.events.publish('services', payload)
        except Exception as error:
            logging.warning('notify_services failed: %s', error)

    def last_error_line(self, service_id: str) -> str:
        try:
            path = self.latest_service_log(service_id)
            if not path.exists():
                return ''
            size = path.stat().st_size
            read_bytes = min(size, 8192)
            with path.open('rb') as f:
                if size > read_bytes:
                    f.seek(size - read_bytes)
                raw = f.read()
            text = raw.decode('utf-8', errors='replace')
            clean = re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', '', text)
            pattern = re.compile(r'\b(error|exception|traceback|fatal|failed|panic|errno)\b', re.IGNORECASE)
            matched = ''
            for line in clean.splitlines():
                if pattern.search(line):
                    matched = line.strip()
            return matched[:200]
        except Exception:
            return ''

    def record_alert(self, pad_id: str, pad_name: str, kind: str, message: str):
        with self.lock:
            self._alert_counter += 1
            alert_id = self._alert_counter
            item = {
                'id': alert_id,
                'time': int(time.time()),
                'pad_id': pad_id,
                'pad_name': pad_name,
                'kind': kind,
                'message': message,
            }
            self.alerts.append(item)
            notifications = self.config.get('notifications', {'crash': True, 'unhealthy': True, 'schedule': True})
            should_publish = True
            if kind in ('crashed', 'restarted', 'gave_up') and not notifications.get('crash', True):
                should_publish = False
            elif kind == 'unhealthy' and not notifications.get('unhealthy', True):
                should_publish = False
            elif kind in ('schedule_failed', 'scene_failed') and not notifications.get('schedule', True):
                should_publish = False

            if should_publish and hasattr(self, 'events'):
                self.events.publish('alert', item)
            return item

    def save(self):
        temporary = self.path.with_suffix('.tmp')
        temporary.write_text(json.dumps(self.config, ensure_ascii=False, indent=2), 'utf-8')
        os.replace(temporary, self.path)
        self.last_activity = time.time()
        if hasattr(self, 'wake'):
            self.wake.set()
        if hasattr(self, 'events'):
            self.notify_services()

    def service(self, service_id):
        for service in self.config['services']:
            if service['id'] == service_id:
                return service
        raise KeyError('서비스를 찾을 수 없습니다.')

    def owned(self, service):
        runtime = service.get('runtime')
        if not runtime:
            return None
        try:
            process = psutil.Process(runtime['pid'])
            if abs(process.create_time() - runtime['created']) < 0.01 and process.is_running():
                return process
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
        return None

    @staticmethod
    def listeners():
        ports = {}
        for connection in psutil.net_connections(kind='tcp'):
            if connection.status == psutil.CONN_LISTEN and connection.pid:
                ports.setdefault(connection.laddr.port, set()).add(connection.pid)
        return ports

    def owned_pids(self):
        pids = set()
        for service in self.config['services']:
            process = self.owned(service)
            if process:
                try:
                    pids |= {process.pid, *(c.pid for c in process.children(recursive=True))}
                except psutil.NoSuchProcess:
                    pass
        return pids

    def external(self, service, ports=None, owned=None):
        """Classify a listener on a stopped pad's port as this project's server or an unrelated one."""
        if not service.get('port') or self.owned(service):
            return None
        ports = self.listeners() if ports is None else ports
        pids = ports.get(service['port'])
        if not pids:
            return None
        owned = self.owned_pids() if owned is None else owned
        pattern = re.compile(re.escape(os.path.normcase(service['cwd'])) + r'(?=[\\"\'\s;]|$)')
        roots, related = {}, False
        for pid in sorted(pids):
            if pid in owned:
                return {'kind': 'conflict', 'pid': pid}
            try:
                listener = psutil.Process(pid)
                chain = [listener]
                while len(chain) < 10:
                    parent = chain[-1].parent()
                    if not parent or parent.name().lower() not in RUNTIMES | LAUNCHERS:
                        break
                    chain.append(parent)
                # Stop at an interactive shell; the terminal itself is not part of the server.
                killable = [listener]
                for process in chain[1:]:
                    if process.name().lower() in LAUNCHERS and not launcher_only(process):
                        break
                    killable.append(process)
                root = listener
                for process in killable:
                    try:
                        if pattern.match(os.path.normcase(process.cwd())) or pattern.search(os.path.normcase(' '.join(process.cmdline()))):
                            related = True
                            # Only project processes may widen the tree, never unrelated parent runtimes.
                            root = process
                    except psutil.AccessDenied:
                        pass
                roots[root.pid] = root.create_time()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                return {'kind': 'conflict', 'pid': pid}
        protected = {os.getpid()}
        try:
            protected |= {p.pid for p in psutil.Process().parents()}
        except psutil.Error:
            pass
        if not related or protected & set(roots):
            return {'kind': 'conflict', 'pid': min(pids)}
        return {'kind': 'external', 'pid': min(pids), 'roots': roots}

    def end_external(self, service):
        found = self.external(service)
        if not found or found['kind'] != 'external':
            raise ValueError(f"포트 {service['port']}를 다른 프로그램이 사용 중입니다. 기존 서버를 확인해 주세요.")
        for pid, created in found['roots'].items():
            try:
                process = psutil.Process(pid)
                if abs(process.create_time() - created) >= 0.01:
                    continue
            except psutil.NoSuchProcess:
                continue
            subprocess.run(['taskkill.exe', '/F', '/T', '/PID', str(pid)], stdin=subprocess.DEVNULL, capture_output=True, timeout=20, creationflags=0x08000000)
        deadline = time.monotonic() + 15
        while port_open(service['port']):
            if time.monotonic() >= deadline:
                raise RuntimeError('외부 실행의 종료를 확인하지 못했습니다. 포트 사용 상태를 확인해 주세요.')
            time.sleep(0.25)
        self.externals.pop(service['id'], None)

    def add(self, values, service_id=None):
        with self.lock:
            data = values.model_dump()
            self.padset(data['padset_id'])
            if data['kind'] == 'docker':
                data['container'] = docker_cli('inspect', '--format', '{{.Id}}', data['container']).strip()
                if any(s.get('kind') == 'docker' and s.get('container') == data['container'] and s['id'] != service_id for s in self.config['services']):
                    raise ValueError('이미 등록된 컨테이너입니다.')
            group = self.member_group(service_id) if service_id else None
            if group:
                data['color'] = group['color']
            allowed = group['member_ids'] if group else [service_id]
            if group and (data['slot'] != group['slot'] or data['padset_id'] != group['padset_id']):
                raise ValueError('그룹 관리에서 패드 위치를 변경해 주세요.')
            if any(s['padset_id'] == data['padset_id'] and s['slot'] == data['slot'] and s['id'] not in allowed for s in self.config['services']):
                raise ValueError('이 패드에는 이미 서비스가 등록되어 있습니다.')
            if service_id:
                self.check_group_busy(service_id)
                service = self.service(service_id)
                if self.owned(service) or (service.get('kind') == 'docker' and self.docker_state(service)['active']):
                    raise ValueError('서비스를 중지한 다음 설정을 변경해 주세요.')
                replace_kind(service, data)
                service.update(runtime=None, error='')
                self.forget_remote(service_id)
            else:
                service = dict(data, id=uuid.uuid4().hex, runtime=None, error='')
                self.config['services'].append(service)
            self.save()
            return service['id']

    def delete(self, service_id):
        with self.lock:
            self.check_group_busy(service_id)
            if self.member_group(service_id):
                raise ValueError('그룹 관리에서 구성을 분리한 다음 삭제해 주세요.')
            service = self.service(service_id)
            if self.owned(service) or (service.get('kind') == 'docker' and self.docker_state(service)['active']):
                raise ValueError('서비스를 중지한 다음 삭제해 주세요.')
            self.config['services'].remove(service)
            self.samples.pop(service_id, None)
            self.history.pop(service_id, None)
            self.forget_remote(service_id)
            self.clean_scenes_for_pad(service_id)
            self.clean_schedules_for_target(service_id)
            shutil.rmtree(self.data_dir / 'services' / service_id, ignore_errors=True)
            self.save()

    def active(self, service_id):
        with self.lock:
            service = self.service(service_id)
            if self.is_remote_service(service):
                return self.remote_status(service_id) in ('running', 'starting', 'unhealthy')
            if service.get('kind') == 'docker':
                return self.docker_state(service)['active']
            return bool(self.owned(service))

    def status_of(self, service_id):
        with self.lock:
            if self.is_remote_service(self.service(service_id)):
                return self.remote_status(service_id)
            if self.service(service_id).get('kind') == 'docker':
                return self.docker_state(self.service(service_id))['status']
            return self.samples.get(service_id, {}).get('status')

    def local_ready(self, service, opener=None):
        """Check a local service's configured readiness probe, or return None when it has none."""
        if not service.get('health_url') and not service.get('port'):
            return None
        if not self.owned(service):
            return False
        try:
            if service.get('health_url'):
                opener = opener or build_opener(ProxyHandler({}))
                with opener.open(Request(service['health_url']), timeout=1) as response:
                    return 200 <= response.status < 400
            return port_open(service['port'])
        except Exception:
            return False

    def restart(self, service_id):
        if self.is_remote(service_id):
            self.stop(service_id)
            self.start(service_id)
            return
        with self.lock:
            self.stop(service_id)
            self.start(service_id)

    def start(self, service_id, takeover=False, auto=False):
        if self.service(service_id).get('kind') == 'docker':
            return self.docker_action(service_id, 'start')
        if self.is_remote(service_id):
            return self.remote_action(service_id, 'start')
        with self.lock:
            # Only a start the user asks for resets the restart history; automatic restarts must count toward restart_max.
            if not auto:
                self.restarts.pop(service_id, None)
            self.check_group_busy(service_id)
            service = self.service(service_id)
            if self.owned(service) or (service.get('kind') == 'docker' and self.docker_state(service)['active']):
                raise ValueError('이미 실행 중인 서비스입니다.')
            if service['port'] and port_open(service['port']):
                if not takeover:
                    raise ValueError(f"포트 {service['port']}를 사용 중입니다. 기존 서버를 확인해 주세요.")
                self.end_external(service)
            if not Path(service['cwd']).is_dir():
                raise ValueError('작업 폴더를 확인해 주세요.')
            self.sync_service_log(service_id)
            s_dir = self.service_dir(service_id)
            log = self.current_service_log(service_id)
            with log.open('a', encoding='utf-8') as output:
                output.write(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] {system_text('서비스 시작')}\n")
            wrapper = s_dir / 'run.cmd'
            command_file = s_dir / 'run.txt'
            command_file.write_text(service['command'] + '\r\n', encoding='utf-8')
            # The batch file never parses the command: it reads it as data and hands it to a child cmd via
            # delayed expansion, so %, quotes and parentheses mean what they mean in a terminal. Redirection
            # applies to the child cmd, so chained commands share the log.
            wrapper.write_text('@echo off\r\nchcp 65001 > nul\r\nset PYTHONIOENCODING=utf-8\r\nset PYTHONUNBUFFERED=1\r\n'
                               f'for /f "usebackq eol= delims=" %%L in ("{command_file}") do set "STACKPAD_COMMAND=%%L"\r\n'
                               'setlocal EnableDelayedExpansion\r\n'
                               f'cmd.exe /d /s /c "!STACKPAD_COMMAND!" < nul >> "{log}" 2>&1\r\n', encoding='utf-8')
            command_line = f'cmd.exe /d /s /c ""{wrapper}""'
            payload = base64.b64encode(json.dumps({'command': command_line, 'cwd': service['cwd']}).encode()).decode()
            script = f"""$ErrorActionPreference='Stop'
$p = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{payload}')) | ConvertFrom-Json
$startup = New-CimInstance -CimClass (Get-CimClass Win32_ProcessStartup) -Property @{{ShowWindow=[uint16]0}} -ClientOnly
$r = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{{CommandLine=$p.command;CurrentDirectory=$p.cwd;ProcessStartupInformation=$startup}}
$r | Select-Object ProcessId,ReturnValue | ConvertTo-Json -Compress
"""
            result = json.loads(powershell(script))
            if result['ReturnValue'] != 0:
                raise RuntimeError(f"서비스 실행 실패: WMI {result['ReturnValue']}")
            try:
                process = psutil.Process(result['ProcessId'])
                created = process.create_time()
            except psutil.NoSuchProcess:
                service.update(runtime=None, error='명령이 곧바로 종료되었습니다. 로그를 확인해 주세요.')
                self.save()
                return
            service.update(runtime={'pid': process.pid, 'created': created, 'log_source': str(log)}, error='')
            self.samples[service_id] = {'status': 'starting'}
            self.save()

    def stop_all_local(self):
        """Stop every running local process and container; remote servers are left alone. Returns names that failed."""
        failed = []
        for service in list(self.config['services']):
            if self.is_remote_service(service):
                continue
            try:
                running = self.owned(service) or (service.get('kind') == 'docker' and self.docker_state(service)['active'])
                if running:
                    self.stop(service['id'])
            except Exception as error:
                logging.error('Stop on shutdown failed for %s: %s', service['name'], error)
                failed.append(service['name'])
        return failed

    def stop(self, service_id):
        if self.service(service_id).get('kind') == 'docker':
            return self.docker_action(service_id, 'stop')
        if self.is_remote(service_id):
            return self.remote_action(service_id, 'stop')
        with self.lock:
            self.restarts.pop(service_id, None)
            self.check_group_busy(service_id)
            service = self.service(service_id)
            process = self.owned(service)
            if process:
                # Capture descendants before killing the tree for post-stop verification.
                descendants = process.children(recursive=True)
                result = subprocess.run(['taskkill.exe', '/F', '/T', '/PID', str(process.pid)], stdin=subprocess.DEVNULL, capture_output=True, timeout=20, creationflags=0x08000000)
                if result.returncode and self.owned(service):
                    raise RuntimeError('종료에 실패했습니다. 프로세스 권한을 확인해 주세요.')
                for child in descendants:
                    try:
                        if child.is_running():
                            child.kill()
                    except psutil.NoSuchProcess:
                        pass
                # Windows can retain process and log handles briefly after taskkill returns.
                _, alive = psutil.wait_procs([process, *descendants], timeout=5)
                if any(target.is_running() for target in alive):
                    raise RuntimeError('프로세스 종료 상태를 확인해 주세요.')
            self.sync_service_log(service_id)
            service.update(runtime=None, error='')
            self.samples.pop(service_id, None)
            self.save()

    def refresh_git_states(self):
        now = time.monotonic()
        with self.lock:
            folders = {s['cwd'] for s in self.config['services']
                       if s.get('kind', 'local') == 'local'
                       and (self.member_group(s['id']) or s).get('environment', 'development') == 'development'}
            for folder in self.git_states.keys() - folders:
                self.git_states.pop(folder, None)
            for folder, future in list(self.git_futures.items()):
                if folder not in folders:
                    if future.cancel():
                        self.git_futures.pop(folder, None)
                    self.git_states.pop(folder, None)
            for folder, future in list(self.git_futures.items()):
                if future.done():
                    if folder in folders:
                        try:
                            self.git_states[folder] = future.result()
                        except Exception:
                            self.git_states[folder] = None
                    self.git_futures.pop(folder, None)
            if self.closed.is_set() or now - self.last_git_check < 10:
                return
            self.last_git_check = now
            for folder in folders:
                if folder not in self.git_futures:
                    future = self.git_pool.submit(self._query_git_state, folder)
                    self.git_futures[folder] = future
                    future.add_done_callback(lambda _: self.wake.set())

    @staticmethod
    def _query_git_state(folder):
        try:
            # A descendant can retain a pipe handle after Git exits. File output
            # keeps timeout cleanup from waiting forever for pipe reader threads.
            with tempfile.TemporaryFile() as output:
                status = subprocess.run(
                    ['git', '--no-optional-locks', '-C', folder, 'status', '--porcelain', '--untracked-files=normal'],
                    stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.DEVNULL,
                    timeout=3, creationflags=0x08000000)
                output.seek(0)
                return ('dirty' if output.read(1) else 'clean') if status.returncode == 0 else None
        except (OSError, subprocess.TimeoutExpired):
            return None

    def snapshot(self):
        with self.lock:
            result = []
            for service in sorted(self.config['services'], key=lambda s: s['slot']):
                if self.is_remote_service(service):
                    result.append(self.remote_snapshot(service))
                    continue
                if service.get('kind') == 'docker':
                    result.append({**service, **self.samples.get(service['id'], {'status': 'checking', 'active': False, 'pid': None, 'uptime': 0}), 'busy': service['id'] in self.docker_busy})
                    continue
                process = self.owned(service)
                sample = self.samples.get(service['id'], {})
                found = None if process else self.externals.get(service['id'])
                if process:
                    status = sample.get('status', 'starting')
                elif sample.get('status') == 'restarting':
                    status = 'restarting'
                elif found:
                    status = found['kind']
                elif service.get('error'):
                    status = 'error'
                else:
                    status = 'stopped'
                result.append({**{k: v for k, v in service.items() if k != 'runtime'}, **sample, 'git_state': self.git_states.get(service['cwd']) if (self.member_group(service['id']) or service).get('environment', 'development') == 'development' else None, 'status': status, 'pid': process.pid if process else None, 'external_pid': found['pid'] if found else None, 'active': bool(process), 'uptime': int(time.time() - process.create_time()) if process else 0})
            return result

    def logs_offset(self, service_id, file=None, offset=None):
        service = self.service(service_id)
        if service.get('kind') == 'docker':
            cid = container_name(service['container'])
            if file != cid or not offset:
                try:
                    output = docker_cli('logs', '--timestamps', '--tail', '300', cid)
                except Exception:
                    output = ''
                lines = output.splitlines(keepends=True)
                clean_lines = []
                last_ts = None
                for line in lines:
                    ts, sep, content = line.partition(' ')
                    if sep:
                        last_ts = ts
                        clean_lines.append(content)
                    else:
                        clean_lines.append(line)
                return {'text': ''.join(clean_lines)[-48000:], 'file': cid, 'offset': last_ts or '', 'reset': True}
            else:
                try:
                    output = docker_cli('logs', '--timestamps', '--since', str(offset), cid)
                except Exception:
                    output = ''
                lines = output.splitlines(keepends=True)
                clean_lines = []
                last_ts = str(offset)
                for line in lines:
                    ts, sep, content = line.partition(' ')
                    if sep and ts > str(offset):
                        last_ts = ts
                        clean_lines.append(content)
                    elif not sep:
                        clean_lines.append(line)
                return {'text': ''.join(clean_lines), 'file': cid, 'offset': last_ts, 'reset': False}

        if self.is_remote(service_id):
            text = self.remote_tail(service_id)
            digest = hashlib.sha256(text.encode('utf-8')).hexdigest()
            if offset == digest:
                return {'unchanged': True, 'text': '', 'offset': digest, 'reset': False}
            return {'unchanged': False, 'text': text, 'offset': digest, 'reset': True}

        self.sync_service_log(service_id)
        path = self.latest_service_log(service_id)
        if not path.exists():
            return {'text': '', 'file': path.name, 'offset': 0, 'reset': True}
        file_size = path.stat().st_size
        try:
            num_offset = int(offset) if offset is not None else None
        except (ValueError, TypeError):
            num_offset = None

        if file != path.name or num_offset is None or num_offset > file_size or num_offset < 0:
            seek_pos = max(0, file_size - 48_000)
            with path.open('rb') as source:
                source.seek(seek_pos)
                raw = source.read()
            if seek_pos > 0:
                idx = 0
                while idx < len(raw) and (raw[idx] & 0xC0) == 0x80:
                    idx += 1
                raw = raw[idx:]
                seek_pos += idx
            valid_len = len(raw)
            while valid_len > 0:
                try:
                    text = raw[:valid_len].decode('utf-8')
                    break
                except UnicodeDecodeError as e:
                    if e.reason == 'unexpected end of data':
                        valid_len = e.start
                    else:
                        text = raw[:valid_len].decode('utf-8', errors='replace')
                        break
            else:
                text = ''
            return {'text': text, 'file': path.name, 'offset': seek_pos + valid_len, 'reset': True}
        else:
            with path.open('rb') as source:
                source.seek(num_offset)
                raw = source.read(256 * 1024)
            valid_len = len(raw)
            while valid_len > 0:
                try:
                    text = raw[:valid_len].decode('utf-8')
                    break
                except UnicodeDecodeError as e:
                    if e.reason == 'unexpected end of data':
                        valid_len = e.start
                    else:
                        text = raw[:valid_len].decode('utf-8', errors='replace')
                        break
            else:
                text = ''
            return {'text': text, 'file': path.name, 'offset': num_offset + valid_len, 'reset': False}

    def tail(self, service_id):
        return self.logs_offset(service_id)['text']

    def sync_service_log(self, service_id):
        with self.lock:
            service = self.service(service_id)
            original = (service.get('runtime') or {}).get('log_source')
            if not original:
                return
            source = Path(original)
            target = self.latest_service_log(service_id)
            if not source.exists() or source.resolve() == target.resolve():
                return
            length = target.stat().st_size if target.exists() else 0
            mode = 'ab' if length <= source.stat().st_size else 'wb'
            with source.open('rb') as input_log, target.open(mode) as output_log:
                if mode == 'ab':
                    input_log.seek(length)
                shutil.copyfileobj(input_log, output_log, length=64 * 1024)

    def pad_folder(self, pad_id):
        with self.lock:
            group = next((g for g in self.config.get('groups', []) if g['id'] == pad_id), None)
            members = [self.service(sid) for sid in group['member_ids']] if group else [self.service(pad_id)]
            folders = [s['cwd'] for s in members if s.get('kind', 'local') == 'local']
            if not folders:
                raise ValueError('원격 서버 패드는 VS Code로 열 수 없습니다.')
        folders = [folder for folder in folders if Path(folder).is_dir()]
        if not folders:
            raise ValueError('작업 폴더를 확인해 주세요.')
        # A group opens the folder its members share, unless they only share a drive root.
        try:
            common = Path(os.path.commonpath(folders))
        except ValueError:
            common = None
        return str(common) if common and common.parent != common else folders[0]

    def open_in_code(self, pad_id):
        folder = self.pad_folder(pad_id)
        code = vscode_path()
        if not code:
            raise ValueError('VS Code 설치 위치를 확인해 주세요.')
        subprocess.Popen([code, folder], cwd=folder, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP, close_fds=True)
        return folder

    def watch(self):
        opener = build_opener(ProxyHandler({}))
        last_purge = time.time()
        last_listeners_time = 0
        cached_ports = {}
        while not self.closed.is_set():
            self.wake.clear()
            self.stats['ticks'] += 1
            if time.time() - last_purge > 3600:
                last_purge = time.time()
                try:
                    self.purge_expired_logs()
                except Exception:
                    pass
            now_time = time.time()
            to_restart = []
            with self.lock:
                for sid, r in list(self.restarts.items()):
                    if r.get('next_at') and now_time >= r['next_at']:
                        if sid not in self.group_operations:
                            to_restart.append(sid)
            for sid in to_restart:
                try:
                    with self.lock:
                        srv = next((s for s in self.config['services'] if s['id'] == sid), None)
                        if srv and not self.owned(srv):
                            r = self.restarts.get(sid)
                            if r:
                                r['next_at'] = 0
                            self.start(sid, auto=True)
                except Exception as error:
                    logging.error('Auto restart execution failed for %s: %s', sid, error)
                    with self.lock:
                        srv = next((s for s in self.config['services'] if s['id'] == sid), None)
                        if srv:
                            srv.update(runtime=None, error=str(error))
                            self.samples[sid] = {'status': 'error', 'message': str(error)}
                            self.save()
                            self.record_alert(sid, srv['name'], 'gave_up', with_error_line('자동 재시작에 실패했습니다.', str(error)))
            with self.lock:
                services = [dict(s) for s in self.config['services'] if s.get('kind', 'local') == 'local']
                containers = [dict(s) for s in self.config['services'] if s.get('kind') == 'docker']
                owned = self.owned_pids()
            has_stopped_port = any(s.get('port') and not self.owned(s) for s in services)
            actively_viewed = (self.events.subscribers > 0) or (time.time() - self.last_services_poll < 10)
            now = time.time()
            if has_stopped_port and (actively_viewed or now - last_listeners_time >= 10):
                try:
                    ports = self.listeners()
                    self.stats['listener_calls'] += 1
                    last_listeners_time = now
                    cached_ports = ports
                except (psutil.Error, OSError):
                    ports = cached_ports
            else:
                ports = cached_ports
            for service in services:
                try:
                    self.sync_service_log(service['id'])
                except (OSError, KeyError):
                    logging.warning('실행 중인 서비스 로그의 새 저장 위치를 확인해 주세요.')
                process = self.owned(service)
                if not process:
                    found = self.external(service, ports, owned)
                    with self.lock:
                        if found:
                            self.externals[service['id']] = found
                        else:
                            self.externals.pop(service['id'], None)
                    with self.lock:
                        current = next((s for s in self.config['services'] if s['id'] == service['id']), None)
                        if current and current.get('runtime') == service.get('runtime') and current.get('runtime'):
                            self.sync_service_log(service['id'])
                            error_line = self.last_error_line(service['id'])
                            policy = current.get('restart_policy', 'never')
                            max_attempts = current.get('restart_max', 3)

                            record = self.restarts.setdefault(service['id'], {'attempts': [], 'next_at': 0})
                            now_time = time.time()
                            record['attempts'] = [t for t in record['attempts'] if now_time - t < 600]

                            can_restart = (
                                policy == 'on-failure'
                                and len(record['attempts']) < max_attempts
                                and service['id'] not in self.group_operations
                            )

                            if can_restart:
                                backoffs = [2, 4, 8, 16, 32, 60]
                                delay = backoffs[min(len(record['attempts']), len(backoffs) - 1)]
                                record['attempts'].append(now_time)
                                record['next_at'] = now_time + delay
                                attempt_num = len(record['attempts'])
                                msg = f"{attempt_num}/{max_attempts} 재시작 대기 중"
                                current.update(runtime=None, error=msg)
                                self.samples[service['id']] = {
                                    'status': 'restarting',
                                    'message': msg,
                                    'error_line': error_line,
                                }
                                self.save()
                                self.record_alert(
                                    service['id'],
                                    service['name'],
                                    'restarted',
                                    msg
                                )
                            else:
                                if policy == 'on-failure' and len(record['attempts']) >= max_attempts:
                                    kind = 'gave_up'
                                    error_msg = '재시작 한도를 초과했습니다. 로그를 확인해 주세요.'
                                else:
                                    kind = 'crashed'
                                    error_msg = '프로세스가 종료되었습니다. 로그를 확인해 주세요.'
                                current.update(runtime=None, error=error_msg)
                                self.samples[service['id']] = {
                                    'status': 'error',
                                    'message': error_msg,
                                    'error_line': error_line,
                                }
                                self.save()
                                self.record_alert(
                                    service['id'],
                                    service['name'],
                                    kind,
                                    with_error_line(error_msg, error_line)
                                )
                    continue
                ready = True
                message = ''
                probe = self.local_ready(service, opener)
                if probe is not None:
                    ready = probe
                if not ready:
                    message = '응답을 확인하고 있습니다.'
                try:
                    processes = [process, *process.children(recursive=True)]
                    memory = sum(p.memory_info().rss for p in processes if p.is_running()) / 1024**2
                    cpu_time = sum(sum(p.cpu_times()[:2]) for p in processes if p.is_running())
                    now = time.monotonic()
                    previous = self.samples.get(service['id'], {})
                    cpu = max(0, (cpu_time - previous.get('_cpu_time', cpu_time)) / max(0.1, now - previous.get('_sample_time', now)) * 100 / (psutil.cpu_count() or 1))
                    age = time.time() - process.create_time()
                    with self.lock:
                        current = next((s for s in self.config['services'] if s['id'] == service['id']), None)
                    sample_status = 'running' if ready else ('starting' if age < 20 else 'unhealthy')
                    if sample_status == 'unhealthy' and service['id'] not in self._last_unhealthy:
                        self._last_unhealthy.add(service['id'])
                        err_line = self.last_error_line(service['id'])
                        self.record_alert(
                            service['id'],
                            service['name'],
                            'unhealthy',
                            with_error_line('응답 이상이 감지되었습니다.', err_line)
                        )
                    elif sample_status == 'running':
                        self._last_unhealthy.discard(service['id'])
                    with self.lock:
                        current = next((s for s in self.config['services'] if s['id'] == service['id']), None)
                        if current and current.get('runtime') == service.get('runtime'):
                            self.samples[service['id']] = {'status': sample_status, 'memory': round(memory, 1), 'cpu': round(cpu, 1), 'message': message, '_cpu_time': cpu_time, '_sample_time': now}
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            for service in containers:
                sample = self.docker_state(service)
                with self.lock:
                    current = next((s for s in self.config['services'] if s['id'] == service['id']), None)
                    if current and current.get('container') == service['container'] and current.get('kind') == 'docker' and service['id'] not in self.docker_busy:
                        self.samples[service['id']] = sample
            self.refresh_git_states()
            self.notify_services()
            now_wall = time.time()
            if self.last_history_tick == 0 or now_wall - self.last_history_tick >= 10:
                self.last_history_tick = now_wall
                with self.lock:
                    for s in services:
                        sid = s['id']
                        proc = self.owned(s)
                        if proc:
                            samp = self.samples.get(sid, {})
                            c = round(float(samp.get('cpu', 0.0)), 1)
                            m = round(float(samp.get('memory', 0.0)), 1)
                        else:
                            c = 0.0
                            m = 0.0
                        self.history.setdefault(sid, deque(maxlen=60)).append((c, m))
            with self.lock:
                has_owned = any(self.owned(s) for s in self.config['services'])
                docker_active = any(s.get('kind') == 'docker' and self.docker_state(s)['active'] for s in self.config['services'])
                has_restarts = any(r.get('next_at') for r in self.restarts.values())
                busy = bool(self.group_operations) or has_restarts or (time.time() - self.last_activity < 15)
            interval = 2 if (has_owned or docker_active or busy) else 10
            self.wake.wait(interval)
        self.git_pool.shutdown(wait=False, cancel_futures=True)

    def service_history(self, pad_id):
        with self.lock:
            group = next((g for g in self.config.get('groups', []) if g['id'] == pad_id), None)
            if group:
                member_ids = group.get('member_ids', [])
                local_members = [mid for mid in member_ids if self.service(mid).get('kind', 'local') == 'local']
                if not local_members:
                    return {'interval': 10, 'cpu': [], 'memory': []}
                member_hists = [list(self.history.get(mid, [])) for mid in local_members]
                max_len = max((len(h) for h in member_hists), default=0)
                if max_len == 0:
                    return {'interval': 10, 'cpu': [], 'memory': []}
                cpu_list = []
                mem_list = []
                for offset in range(max_len, 0, -1):
                    c_sum = 0.0
                    m_sum = 0.0
                    for h in member_hists:
                        if len(h) >= offset:
                            c_sum += h[-offset][0]
                            m_sum += h[-offset][1]
                    cpu_list.append(round(c_sum, 1))
                    mem_list.append(round(m_sum, 1))
                return {'interval': 10, 'cpu': cpu_list, 'memory': mem_list}
            service = next((s for s in self.config['services'] if s['id'] == pad_id), None)
            if not service:
                raise KeyError('서비스를 찾을 수 없습니다.')
            if service.get('kind', 'local') != 'local':
                return {'interval': 10, 'cpu': [], 'memory': []}
            hist = list(self.history.get(pad_id, []))
            return {
                'interval': 10,
                'cpu': [h[0] for h in hist],
                'memory': [h[1] for h in hist],
            }

    @property
    def startup_path(self):
        return Path(os.environ['APPDATA']) / 'Microsoft/Windows/Start Menu/Programs/Startup/StackPad.lnk'

    def autostart(self, enabled):
        if enabled:
            if self.desktop_exe:
                target, arguments = self.desktop_exe, '--hidden'
            elif getattr(sys, 'frozen', False):
                target, arguments = sys.executable, ''
            else:
                target = str(Path(sys.executable).with_name('pythonw.exe'))
                arguments = subprocess.list2cmdline([str(Path(__file__).with_name('main.py')), '--data-dir', str(getattr(self, 'bootstrap_dir', self.data_dir))])
            payload = base64.b64encode(json.dumps({'target': target, 'arguments': arguments, 'link': str(self.startup_path)}).encode()).decode()
            powershell(f"""$ErrorActionPreference='Stop'
$p=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{payload}')) | ConvertFrom-Json
$shell=New-Object -ComObject WScript.Shell
$link=$shell.CreateShortcut($p.link)
$link.TargetPath=$p.target
$link.Arguments=$p.arguments
$link.WorkingDirectory=Split-Path $p.target -Parent
$link.Description='{system_text('StackPad 자동 실행')}'
$link.Save()
""")
        else:
            self.startup_path.unlink(missing_ok=True)
