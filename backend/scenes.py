"""Scenes allow starting and stopping multiple pads across padsets in order."""
import threading
import uuid
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator


class SceneInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1, max_length=40)
    color: str = '#10b981'
    pad_ids: list[str] = Field(default_factory=list, max_length=16)

    @field_validator('name')
    @classmethod
    def name_line(cls, value):
        value = value.strip()
        if not value or any(c in value for c in ('\x00', '\n', '\r')):
            raise ValueError('흐름 이름을 한 줄로 입력해 주세요.')
        return value


class SceneManager:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.scene_progress = {}
        self.scene_threads = {}

    def get_scenes(self):
        with self.lock:
            return [dict(s) for s in self.config.get('scenes', [])]

    def get_scene(self, scene_id: str):
        with self.lock:
            for scene in self.config.get('scenes', []):
                if scene['id'] == scene_id:
                    return dict(scene)
        raise KeyError('등록되지 않은 흐름입니다.')

    def save_scene(self, scene_id: str | None, values: SceneInput):
        with self.lock:
            scenes = self.config.setdefault('scenes', [])
            if scene_id:
                target = None
                for s in scenes:
                    if s['id'] == scene_id:
                        target = s
                        break
                if not target:
                    raise KeyError('등록되지 않은 흐름입니다.')
                target['name'] = values.name
                target['color'] = values.color
                target['pad_ids'] = list(values.pad_ids)
                res = dict(target)
            else:
                new_id = str(uuid.uuid4())
                entry = {
                    'id': new_id,
                    'name': values.name,
                    'color': values.color,
                    'pad_ids': list(values.pad_ids),
                }
                scenes.append(entry)
                res = dict(entry)
            self.save()
        self.notify_services()
        return res

    def delete_scene(self, scene_id: str):
        with self.lock:
            scenes = self.config.get('scenes', [])
            before_len = len(scenes)
            self.config['scenes'] = [s for s in scenes if s['id'] != scene_id]
            if len(self.config['scenes']) == before_len:
                raise KeyError('등록되지 않은 흐름입니다.')
            self.save()
        self.notify_services()
        return {'ok': True}

    def clean_scenes_for_pad(self, pad_id: str):
        with self.lock:
            changed = False
            for scene in self.config.get('scenes', []):
                if pad_id in scene.get('pad_ids', []):
                    scene['pad_ids'] = [pid for pid in scene['pad_ids'] if pid != pad_id]
                    changed = True
            if changed:
                self.save()

    def is_pad_active(self, pad_id: str) -> bool:
        # Returns True if pad is running / partially running
        for group in self.config.get('groups', []):
            if group['id'] == pad_id:
                for mid in group.get('member_ids', []):
                    for s in self.config.get('services', []):
                        if s['id'] == mid and self.is_service_active(s):
                            return True
                return False
        for s in self.config.get('services', []):
            if s['id'] == pad_id:
                return self.is_service_active(s)
        return False

    def is_service_active(self, service: dict) -> bool:
        if self.owned(service):
            return True
        if service.get('kind') == 'docker' and service.get('active'):
            return True
        if service.get('kind') == 'remote' and service.get('active'):
            return True
        return False

    def scene_action(self, scene_id: str, action: Literal['start', 'stop']):
        scene = self.get_scene(scene_id)
        thread = threading.Thread(
            target=self._run_scene_action,
            args=(scene, action),
            name=f"scene-{action}-{scene_id}",
            daemon=True
        )
        self.scene_threads[scene_id] = thread
        thread.start()
        return {'ok': True, 'scene_id': scene_id, 'action': action}

    def _run_scene_action(self, scene: dict, action: Literal['start', 'stop']):
        scene_id = scene['id']
        scene_name = scene['name']
        pad_ids = list(scene.get('pad_ids', []))
        if action == 'stop':
            pad_ids.reverse()

        total = len(pad_ids)
        self.scene_progress[scene_id] = {
            'done': 0,
            'total': total,
            'current_id': None,
            'phase': 'starting' if action == 'start' else 'stopping'
        }
        self.events.publish('progress', {'scene_id': scene_id, **self.scene_progress[scene_id]})

        try:
            for idx, pid in enumerate(pad_ids):
                self.scene_progress[scene_id]['done'] = idx
                self.scene_progress[scene_id]['current_id'] = pid
                self.events.publish('progress', {'scene_id': scene_id, **self.scene_progress[scene_id]})

                is_group = any(g['id'] == pid for g in self.config.get('groups', []))
                active = self.is_pad_active(pid)

                if action == 'start':
                    if active:
                        continue
                    try:
                        if is_group:
                            self.group_action(pid, 'start')
                        else:
                            self.start(pid)
                    except Exception as err:
                        pad_name = self.get_pad_name(pid)
                        self.record_alert(
                            pad_id=pid,
                            pad_name=pad_name,
                            kind='scene_failed',
                            message=f"흐름 '{scene_name}' 실행 중 '{pad_name}' 시작 실패: {err}"
                        )
                elif action == 'stop':
                    if not active:
                        continue
                    try:
                        if is_group:
                            self.group_action(pid, 'stop')
                        else:
                            self.stop(pid)
                    except Exception as err:
                        pad_name = self.get_pad_name(pid)
                        self.record_alert(
                            pad_id=pid,
                            pad_name=pad_name,
                            kind='scene_failed',
                            message=f"흐름 '{scene_name}' 정지 중 '{pad_name}' 정지 실패: {err}"
                        )
        finally:
            self.scene_progress.pop(scene_id, None)
            self.events.publish('progress', {'scene_id': scene_id, 'done': total, 'total': total, 'finished': True})
            self.notify_services()

    def get_pad_name(self, pad_id: str) -> str:
        for g in self.config.get('groups', []):
            if g['id'] == pad_id:
                return g.get('name', 'Group')
        for s in self.config.get('services', []):
            if s['id'] == pad_id:
                return s.get('name', 'Service')
        return pad_id
