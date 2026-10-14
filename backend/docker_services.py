"""Control existing local containers without invoking a shell or exposing inspect secrets."""
import json
import os
import re
import subprocess
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator
from groups import PAD_COLORS


def container_name(value):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,254}', value):
        raise ValueError('도커 컨테이너 이름 또는 ID를 입력해 주세요.')
    return value


class DockerServiceInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    kind: Literal['docker'] = 'docker'
    name: str = Field(min_length=1, max_length=40)
    container: str
    slot: int = Field(ge=0, le=15)
    padset_id: str = 'default'
    color: str = '#22c55e'
    autostart: bool = False

    @field_validator('container')
    @classmethod
    def target(cls, value):
        return container_name(value.strip())

    @field_validator('name')
    @classmethod
    def clean(cls, value):
        value = value.strip()
        if not value or any(c in value for c in ('\x00', '\n', '\r')):
            raise ValueError('서비스 이름을 한 줄로 입력해 주세요.')
        return value

    @field_validator('color')
    @classmethod
    def color_value(cls, value):
        if value not in PAD_COLORS:
            raise ValueError('제공된 패드 색상을 선택해 주세요.')
        return value


def docker_cli(*args):
    try:
        result = subprocess.run(['docker', 'container', *args], stdin=subprocess.DEVNULL,
                                capture_output=True, timeout=25, encoding='utf-8', errors='replace',
                                creationflags=0x08000000 if os.name == 'nt' else 0)
    except FileNotFoundError:
        raise ValueError('Docker 설치와 PATH 설정을 확인해 주세요.') from None
    except subprocess.TimeoutExpired:
        raise ValueError('Docker 응답 시간이 초과되었습니다. 데몬 연결을 확인해 주세요.') from None
    if result.returncode:
        raise ValueError('Docker 데몬 연결과 컨테이너 상태를 확인해 주세요.')
    return result.stdout + (result.stderr if args[0] == 'logs' else '')


class DockerServices:
    def docker_containers(self):
        rows = [json.loads(line) for line in docker_cli('ls', '--all', '--no-trunc', '--format', '{{json .}}').splitlines() if line]
        return [{'id': r['ID'], 'name': r['Names'], 'image': r['Image'], 'status': r['Status']} for r in rows]

    def docker_state(self, service):
        try:
            info = json.loads(docker_cli('inspect', '--format', '{"state":{{json .State}},"name":{{json .Name}},"ports":{{json .NetworkSettings.Ports}}}', container_name(service['container'])))
            state = info['state']
            ports = []
            for exposed, bindings in (info['ports'] or {}).items():
                values = [binding['HostPort'] for binding in bindings] if bindings else [exposed.split('/')[0]]
                for value in values:
                    label = value + ('/udp' if exposed.endswith('/udp') else '')
                    if label not in ports:
                        ports.append(label)
            active = bool(state.get('Running'))
            status = 'running' if active else 'error' if state.get('ExitCode', 0) or state.get('Dead') else 'stopped'
            if state.get('Paused') or state.get('Health', {}).get('Status') == 'unhealthy':
                status = 'unhealthy'
            elif state.get('Restarting') or state.get('Health', {}).get('Status') == 'starting':
                status = 'starting'
            uptime = 0
            if active:
                try:
                    uptime = max(0, int(datetime.now().timestamp() - datetime.fromisoformat(state['StartedAt'].replace('Z', '+00:00')).timestamp()))
                except (ValueError, KeyError):
                    pass
            return {'status': status, 'active': active, 'pid': None, 'uptime': uptime, 'container_name': info['name'].lstrip('/'), 'container_ports': ports, 'message': '일시 정지된 컨테이너입니다.' if state.get('Paused') else '', 'error': state.get('Error', '')}
        except (ValueError, KeyError, TypeError, AttributeError):
            return {'status': 'unreachable', 'active': False, 'pid': None, 'uptime': 0, 'message': 'Docker 데몬 연결과 컨테이너 상태를 확인해 주세요.'}

    def docker_action(self, service_id, action):
        with self.lock:
            self.check_group_busy(service_id)
            service = dict(self.service(service_id))
            if service_id in self.docker_busy:
                raise ValueError('컨테이너 작업을 완료한 뒤 다시 시도해 주세요.')
            self.docker_busy.add(service_id)
        try:
            docker_cli(action, container_name(service['container']))
            sample = self.docker_state(service)
            if sample['status'] == 'unreachable' or (action == 'start' and not sample['active']) or (action == 'stop' and sample['active']):
                raise ValueError('컨테이너 실행 결과를 확인해 주세요.')
            with self.lock:
                self.samples[service_id] = sample
        finally:
            with self.lock:
                self.docker_busy.discard(service_id)
