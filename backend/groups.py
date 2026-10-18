"""Groups retain individual commands, process ownership and log files."""
import threading
import time
import uuid
import copy
import os
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator

from remote import RemoteSpec

PAD_COLORS = ('#ef4444', '#da9281', '#f97316', '#be9537', '#e6d3a8', '#facc15', '#daf797', '#22c55e', '#97f7da', '#25bfd0', '#3b82f6', '#a8bbe6', '#a855f7', '#ef3994', '#eea0c7', '#f5f5f4')



# Earlier palette colors mapped by role, so an orange pad stays orange.
LEGACY_COLORS = {'#75d9a5': '#97f7da', '#f2ad62': '#f97316', '#7db5eb': '#3b82f6', '#c8a0ee': '#a855f7', '#ee8e9c': '#eea0c7', '#dfcf76': '#facc15',
                 '#6fd3d1': '#25bfd0', '#9aa5f2': '#a8bbe6', '#b8d977': '#daf797', '#f29a76': '#da9281', '#e7a6d8': '#ef3994', '#b4bcc0': '#f5f5f4',
                 '#e86f6f': '#ef4444', '#c99a6e': '#be9537', '#a77bd9': '#a855f7', '#ece4cf': '#e6d3a8'}

def _lab(color):
    rgb = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    r, g, b = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    xyz = ((0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047, 0.2126 * r + 0.7152 * g + 0.0722 * b, (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883)
    fx, fy, fz = [t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116 for t in xyz]
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


def nearest_color(color):
    """Map a color from an older palette to the closest current pad color."""
    if color in PAD_COLORS:
        return color
    if color in LEGACY_COLORS:
        return LEGACY_COLORS[color]
    try:
        source = _lab(color)
    except (ValueError, IndexError):
        return PAD_COLORS[0]
    return min(PAD_COLORS, key=lambda c: sum((x - y) ** 2 for x, y in zip(_lab(c), source)))

class GroupInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1, max_length=40)
    member_ids: list[str] = Field(min_length=2, max_length=16)
    slot: int = Field(ge=0, le=15)
    padset_id: str = 'default'
    color: str = '#22c55e'
    wait_ready: bool = False
    autostart: bool = False

    @field_validator('name')
    @classmethod
    def name_line(cls, value):
        value = value.strip()
        if not value or any(c in value for c in ('\x00', '\n', '\r')):
            raise ValueError('그룹 이름을 한 줄로 입력해 주세요.')
        return value

    @field_validator('member_ids')
    @classmethod
    def unique_members(cls, value):
        if len(set(value)) != len(value):
            raise ValueError('구성을 중복으로 선택했습니다.')
        return value

    @field_validator('color')
    @classmethod
    def pad_color(cls, value):
        if value not in PAD_COLORS:
            raise ValueError('제공된 패드 색상을 선택해 주세요.')
        return value


class ComponentInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: str | None = None
    kind: Literal['local', 'remote', 'docker'] = 'local'
    name: str = Field(min_length=1, max_length=40)
    command: str = Field(default='', max_length=2000)
    cwd: str = Field(default='', max_length=500)
    port: int | None = Field(default=None, ge=1, le=65535)
    health_url: str = Field(default='', max_length=1000)
    remote: RemoteSpec | None = None
    container: str = ''
    restart_policy: Literal['never', 'on-failure'] = 'never'
    restart_max: int = Field(default=3, ge=1, le=10)


class PadInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1, max_length=40)
    slot: int = Field(ge=0, le=15)
    padset_id: str = 'default'
    color: str = '#22c55e'
    autostart: bool = False
    wait_ready: bool = False
    components: list[ComponentInput] = Field(min_length=1, max_length=16)
    domain_url: str = Field(default='', max_length=1000)
    local_url: str = Field(default='', max_length=1000)

    @field_validator('name')
    @classmethod
    def name_line(cls, value):
        value = value.strip()
        if not value or any(c in value for c in ('\x00', '\n', '\r')):
            raise ValueError('한 줄로 입력해 주세요.')
        return value

    @field_validator('domain_url')
    @classmethod
    def domain(cls, value):
        value = value.strip()
        if value:
            url = urlsplit(value)
            if url.scheme not in ('http', 'https') or not url.hostname or url.username or url.password:
                raise ValueError('도메인 URL은 http 또는 https 주소로 입력해 주세요.')
        return value

    @field_validator('local_url')
    @classmethod
    def local(cls, value):
        value = value.strip()
        if value:
            url = urlsplit(value)
            if url.scheme not in ('http', 'https') or url.hostname not in LOOPBACK or url.username or url.password:
                raise ValueError('로컬 URL은 localhost 또는 127.0.0.1 주소로 입력해 주세요.')
        return value


LOOPBACK = ('localhost', '127.0.0.1', '::1')
LINK_KEYS = ('domain_url', 'local_url')


def automatic_local_url(members):
    """The last local member with a port is usually the frontend; a health URL ending in / is a page worth opening."""
    for service in reversed(members):
        if service.get('kind') == 'remote' or not service.get('port'):
            continue
        health = urlsplit(service.get('health_url') or '')
        if health.hostname in LOOPBACK and health.port == service['port'] and health.path.endswith('/'):
            return f'{health.scheme}://{health.netloc}{health.path}'
        return f"http://localhost:{service['port']}/"
    return ''


class GroupManager:
    def delete_pad(self, pad_id):
        with self.lock:
            group = next((g for g in self.config.get('groups', []) if g['id'] == pad_id), None)
            ids = group['member_ids'] if group else [pad_id]
            if not group and self.member_group(pad_id):
                raise ValueError('전체 패드의 설정에서 삭제해 주세요.')
            for sid in ids:
                self.check_group_busy(sid)
                if self.owned(self.service(sid)) or (self.service(sid).get('kind') == 'docker' and self.docker_state(self.service(sid))['active']):
                    raise ValueError('패드를 중지한 다음 삭제해 주세요.')
            previous = copy.deepcopy(self.config)
            try:
                self.config['services'] = [s for s in self.config['services'] if s['id'] not in ids]
                self.config['groups'] = [g for g in self.config.get('groups', []) if g['id'] != pad_id]
                self.save()
            except Exception:
                self.config = previous
                raise
            for sid in ids:
                self.samples.pop(sid, None)
                self.forget_remote(sid)

    def save_pad(self, values, pad_id=None):
        # Import after engine module initialization; reuse the existing command validation.
        from engine import RemoteServiceInput, ServiceInput
        from docker_services import DockerServiceInput
        from remote import LOCAL_KEYS
        with self.lock:
            self.padset(values.padset_id)
            old_group = next((g for g in self.config.get('groups', []) if g['id'] == pad_id), None)
            old_ids = old_group['member_ids'][:] if old_group else [pad_id] if pad_id else []
            old_services = [self.service(sid) for sid in old_ids]
            if pad_id and not old_group and self.member_group(pad_id):
                raise ValueError('구성이 속한 패드의 설정에서 변경해 주세요.')
            for service in old_services:
                self.check_group_busy(service['id'])
                if self.owned(service) or (service.get('kind') == 'docker' and self.docker_state(service)['active']):
                    raise ValueError('패드를 중지한 다음 설정을 변경해 주세요.')
            if any(s['padset_id'] == values.padset_id and s['slot'] == values.slot and s['id'] not in old_ids for s in self.config['services']):
                raise ValueError('이 패드에는 이미 서비스가 등록되어 있습니다.')
            supplied = [c.id for c in values.components if c.id]
            if len(set(supplied)) != len(supplied) or any(sid not in old_ids for sid in supplied):
                raise ValueError('이 패드에 속한 구성만 편집할 수 있습니다.')
            validated = []
            for c in values.components:
                if c.kind == 'remote':
                    if not c.remote:
                        raise ValueError('원격 서버의 호스트와 명령을 입력해 주세요.')
                    validated.append(RemoteServiceInput(name=c.name, remote=c.remote, slot=values.slot, color=values.color).model_dump())
                elif c.kind == 'docker':
                    data = DockerServiceInput(name=c.name, container=c.container, slot=values.slot, color=values.color, autostart=values.autostart, padset_id=values.padset_id).model_dump()
                    from docker_services import docker_cli
                    data['container'] = docker_cli('inspect', '--format', '{{.Id}}', data['container']).strip()
                    if any(s.get('kind') == 'docker' and s.get('container') == data['container'] and s['id'] not in old_ids for s in self.config['services']) or any(s.get('container') == data['container'] for s in validated):
                        raise ValueError('이미 등록된 컨테이너입니다.')
                    validated.append(data)
                else:
                    validated.append(ServiceInput(name=c.name, command=c.command, cwd=c.cwd, port=c.port, health_url=c.health_url, slot=values.slot, color=values.color, autostart=values.autostart, restart_policy=c.restart_policy, restart_max=c.restart_max).model_dump())
            for data in validated:
                data['padset_id'] = values.padset_id
            prepared = []
            for component, data in zip(values.components, validated):
                existing = self.service(component.id) if component.id else None
                # A component that switched kind keeps its id and log but not the other kind's settings.
                kept = {k: v for k, v in (existing or {}).items() if k not in (*LOCAL_KEYS, 'remote', 'container', *LINK_KEYS)}
                prepared.append({**kept, **data, 'id': component.id or uuid.uuid4().hex, 'runtime': None, 'error': ''})
            group = None
            if len(prepared) > 1:
                result_id = old_group['id'] if old_group else uuid.uuid4().hex
                group = GroupInput(name=values.name, member_ids=[s['id'] for s in prepared], slot=values.slot, color=values.color, autostart=values.autostart, wait_ready=values.wait_ready).model_dump()
                group['id'] = result_id
                group['padset_id'] = values.padset_id
                # Group management saves only GroupInput, so the links live outside it.
                group.update(domain_url=values.domain_url, local_url=values.local_url)
            else:
                prepared[0]['name'] = values.name.strip()
                prepared[0].update(domain_url=values.domain_url, local_url=values.local_url)
                result_id = prepared[0]['id']
            previous = copy.deepcopy(self.config)
            try:
                self.config['services'] = [s for s in self.config['services'] if s['id'] not in old_ids] + prepared
                self.config['groups'] = [g for g in self.config.get('groups', []) if not old_group or g['id'] != old_group['id']]
                if group:
                    self.config['groups'].append(group)
                self.save()
            except Exception:
                self.config = previous
                raise
            for sid in old_ids:
                self.samples.pop(sid, None)
                self.forget_remote(sid)
            return result_id

    def move_pad(self, pad_id, slot, padset_id=None):
        with self.lock:
            group = next((g for g in self.config.get('groups', []) if g['id'] == pad_id), None)
            members = [self.service(sid) for sid in group['member_ids']] if group else [self.service(pad_id)]
            if not group and self.member_group(pad_id):
                raise ValueError('구성별 이동 대신 전체 패드를 이동해 주세요.')
            padset_id = padset_id or members[0]['padset_id']
            self.padset(padset_id)
            ids = {s['id'] for s in members}
            if any(s['padset_id'] == padset_id and s['slot'] == slot and s['id'] not in ids for s in self.config['services']):
                raise ValueError('빈 패드로 이동해 주세요.')
            previous = copy.deepcopy(self.config)
            try:
                for service in members:
                    service['slot'] = slot
                    service['padset_id'] = padset_id
                if group:
                    group['slot'] = slot
                    group['padset_id'] = padset_id
                self.save()
            except Exception:
                self.config = previous
                raise

    def pad_links(self):
        """Domain and local addresses for every pad, keyed by pad id; empty strings hide the menu items."""
        with self.lock:
            grouped = {sid for g in self.config.get('groups', []) for sid in g['member_ids']}
            pads = [(g, [self.service(sid) for sid in g['member_ids']]) for g in self.config.get('groups', [])]
            pads += [(s, [s]) for s in self.config['services'] if s['id'] not in grouped]
            return {pad['id']: {'domain': pad.get('domain_url', ''), 'local': pad.get('local_url') or automatic_local_url(members)} for pad, members in pads}

    def open_link(self, pad_id, target):
        url = self.pad_links().get(pad_id, {}).get(target)
        if url is None:
            raise KeyError('패드를 찾을 수 없습니다.')
        if not url:
            raise ValueError('패드 설정에서 열 주소를 입력해 주세요.')
        os.startfile(url)
        return url

    def group(self, group_id):
        for group in self.config.get('groups', []):
            if group['id'] == group_id:
                return group
        raise KeyError('그룹을 찾을 수 없습니다.')

    def member_group(self, service_id):
        return next((g for g in self.config.get('groups', []) if service_id in g['member_ids']), None)

    def check_group_busy(self, service_id):
        if service_id in self.docker_busy:
            raise ValueError('컨테이너 작업을 완료한 뒤 다시 시도해 주세요.')
        owner = self.group_operations.get(service_id)
        if owner is not None and owner != threading.get_ident():
            raise ValueError('그룹 작업이 진행 중입니다. 완료 후 다시 시도해 주세요.')

    def save_group(self, values, group_id=None):
        with self.lock:
            data = values.model_dump()
            self.padset(data['padset_id'])
            if any(self.service(sid)['padset_id'] != data['padset_id'] for sid in data['member_ids']):
                raise ValueError('같은 패드셋의 구성으로 패드를 만들어 주세요.')
            old = self.group(group_id) if group_id else None
            affected = set(data['member_ids']) | set(old['member_ids'] if old else [])
            for sid in affected:
                service = self.service(sid)
                self.check_group_busy(sid)
                if old and (self.owned(service) or (service.get('kind') == 'docker' and self.docker_state(service)['active'])):
                    raise ValueError('그룹을 중지한 다음 구성을 변경해 주세요.')
                other = self.member_group(sid)
                if other and other['id'] != group_id:
                    raise ValueError('다른 그룹에 속한 구성입니다.')
            if any(s['padset_id'] == data['padset_id'] and s['slot'] == data['slot'] and s['id'] not in affected for s in self.config['services']):
                raise ValueError('이 패드에는 이미 서비스가 등록되어 있습니다.')
            occupied = {s['slot'] for s in self.config['services'] if s['id'] not in affected and s['padset_id'] == data['padset_id']} | {data['slot']}
            available = [slot for slot in range(16) if slot not in occupied]
            removed = sorted(affected - set(data['member_ids']))
            if len(available) < len(removed):
                raise ValueError('분리할 구성에 필요한 빈 패드를 확보해 주세요.')
            for sid, slot in zip(removed, available):
                self.service(sid)['slot'] = slot
            for sid in data['member_ids']:
                self.service(sid)['slot'] = data['slot']
                self.service(sid)['color'] = data['color']
            if old:
                old.update(data)
                result = old['id']
            else:
                result = uuid.uuid4().hex
                self.config.setdefault('groups', []).append(dict(data, id=result))
            self.save()
            return result

    def dissolve_group(self, group_id):
        with self.lock:
            group = self.group(group_id)
            members = [self.service(sid) for sid in group['member_ids']]
            for service in members:
                self.check_group_busy(service['id'])
            if any(self.owned(s) or (s.get('kind') == 'docker' and self.docker_state(s)['active']) for s in members):
                raise ValueError('그룹을 중지한 다음 해제해 주세요.')
            occupied = {s['slot'] for s in self.config['services'] if s['id'] not in group['member_ids'] and s['padset_id'] == group['padset_id']}
            available = [group['slot'], *[s for s in range(16) if s not in occupied and s != group['slot']]]
            if len(available) < len(members):
                raise ValueError('구성별로 사용할 빈 패드를 확보해 주세요.')
            for service, slot in zip(members, available):
                service['slot'] = slot
            self.config['groups'].remove(group)
            self.save()

    def group_action(self, group_id, action, takeover=False, skip_remote=False):
        with self.lock:
            group = dict(self.group(group_id))
            # Windows startup leaves remote members to their own servers.
            ids = [sid for sid in group['member_ids'] if not (skip_remote and self.is_remote_service(self.service(sid)))]
            for sid in ids:
                if sid in self.group_operations:
                    raise ValueError('그룹 작업이 진행 중입니다.')
            for sid in ids:
                self.group_operations[sid] = threading.get_ident()
        started = []
        try:
            if action == 'stop':
                errors = []
                for sid in reversed(ids):
                    try:
                        self.stop(sid)
                    except Exception as error:
                        errors.append(f"{self.service(sid)['name']}: {error}")
                if errors:
                    raise ValueError('\n'.join(errors))
                return
            for sid in ids:
                if not self.active(sid):
                    self.start(sid, takeover=takeover)
                    started.append(sid)
                    if not self.active(sid):
                        raise ValueError(f"{self.service(sid)['name']}: 실행에 실패했습니다. 로그를 확인해 주세요.")
                if group['wait_ready']:
                    deadline = time.monotonic() + 30
                    while True:
                        with self.lock:
                            active = self.active(sid)
                            ready = self.status_of(sid) == 'running'
                        if not active:
                            raise ValueError(f"{self.service(sid)['name']}: 실행이 종료되었습니다. 로그를 확인해 주세요.")
                        if ready:
                            break
                        if time.monotonic() >= deadline or self.closed.wait(.2):
                            raise ValueError(f"{self.service(sid)['name']}: 준비 확인 시간이 초과되었습니다.")
        except Exception as error:
            cleanup_errors = []
            for sid in reversed(started):
                try:
                    self.stop(sid)
                except Exception as cleanup:
                    cleanup_errors.append(str(cleanup))
            if cleanup_errors:
                raise ValueError(f'{error}\n시작한 구성의 종료 상태를 확인해 주세요: ' + '; '.join(cleanup_errors)) from error
            raise
        finally:
            with self.lock:
                for sid in ids:
                    self.group_operations.pop(sid, None)
