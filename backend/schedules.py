"""Schedules execute pads and scenes at configured times and days."""
import copy
import datetime
import threading
import uuid
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator


class ScheduleInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    target_type: Literal['scene', 'pad']
    target_id: str
    action: Literal['start', 'stop']
    time: str = Field(pattern=r'^\d{2}:\d{2}$')
    days: list[int] = Field(default_factory=lambda: list(range(7)))
    enabled: bool = True

    @field_validator('time')
    @classmethod
    def validate_time(cls, v):
        parts = v.split(':')
        if len(parts) != 2:
            raise ValueError('HH:MM 형식으로 입력해 주세요.')
        try:
            h, m = int(parts[0]), int(parts[1])
        except ValueError:
            raise ValueError('HH:MM 형식으로 입력해 주세요.')
        if not (0 <= h <= 23 and 0 <= m <= 59):
            raise ValueError('올바른 시각(00:00~23:59)을 입력해 주세요.')
        return f"{h:02d}:{m:02d}"

    @field_validator('days')
    @classmethod
    def validate_days(cls, v):
        if not v:
            raise ValueError('요일을 하나 이상 선택해 주세요.')
        if any(d < 0 or d > 6 for d in v):
            raise ValueError('요일 값은 0부터 6 사이여야 합니다.')
        return sorted(list(set(v)))


class ScheduleManager:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.schedule_last_run = {}
        self.scheduler_thread = None

    def start_scheduler(self):
        if self.scheduler_thread is None or not self.scheduler_thread.is_alive():
            self.scheduler_thread = threading.Thread(
                target=self._scheduler_loop,
                name="scheduler-loop",
                daemon=True
            )
            self.scheduler_thread.start()

    def _scheduler_loop(self):
        while not self.closed.is_set():
            try:
                self.check_schedules()
            except Exception as e:
                import logging
                logging.error('Scheduler check error: %s', e)
            self.wake.wait(30.0)

    def get_schedules(self):
        with self.lock:
            return [dict(s) for s in self.config.get('schedules', [])]

    def get_schedule(self, schedule_id: str):
        with self.lock:
            for s in self.config.get('schedules', []):
                if s['id'] == schedule_id:
                    return dict(s)
        raise KeyError('등록되지 않은 예약입니다.')

    def save_schedule(self, schedule_id: str | None, values: ScheduleInput):
        with self.lock:
            schedules = self.config.setdefault('schedules', [])
            if schedule_id:
                target = None
                for s in schedules:
                    if s['id'] == schedule_id:
                        target = s
                        break
                if not target:
                    raise KeyError('등록되지 않은 예약입니다.')
                target['target_type'] = values.target_type
                target['target_id'] = values.target_id
                target['action'] = values.action
                target['time'] = values.time
                target['days'] = list(values.days)
                target['enabled'] = values.enabled
                res = dict(target)
            else:
                new_id = str(uuid.uuid4())
                entry = {
                    'id': new_id,
                    'target_type': values.target_type,
                    'target_id': values.target_id,
                    'action': values.action,
                    'time': values.time,
                    'days': list(values.days),
                    'enabled': values.enabled,
                }
                schedules.append(entry)
                res = dict(entry)
            self.save()
        self.notify_services()
        return res

    def delete_schedule(self, schedule_id: str):
        with self.lock:
            schedules = self.config.get('schedules', [])
            before_len = len(schedules)
            self.config['schedules'] = [s for s in schedules if s['id'] != schedule_id]
            if len(self.config['schedules']) == before_len:
                raise KeyError('등록되지 않은 예약입니다.')
            self.save()
        self.notify_services()
        return {'ok': True}

    def toggle_schedule(self, schedule_id: str, enabled: bool):
        with self.lock:
            for s in self.config.get('schedules', []):
                if s['id'] == schedule_id:
                    s['enabled'] = enabled
                    self.save()
                    self.notify_services()
                    return dict(s)
        raise KeyError('등록되지 않은 예약입니다.')

    def clean_schedules_for_target(self, target_id: str):
        with self.lock:
            schedules = self.config.get('schedules', [])
            self.config['schedules'] = [s for s in schedules if s.get('target_id') != target_id]
            self.save()

    def check_schedules(self, now: datetime.datetime | None = None):
        if now is None:
            now = datetime.datetime.now()

        current_weekday = now.weekday()
        current_time_str = now.strftime('%H:%M')
        today_date_str = now.strftime('%Y-%m-%d')

        schedules = self.get_schedules()
        for sched in schedules:
            if not sched.get('enabled', True):
                continue
            if current_weekday not in sched.get('days', []):
                continue

            sched_time = sched.get('time')
            if not sched_time:
                continue

            # Compare target time today
            try:
                sh, sm = [int(p) for p in sched_time.split(':')]
                target_dt = now.replace(hour=sh, minute=sm, second=0, microsecond=0)
            except Exception:
                continue

            diff_sec = (now - target_dt).total_seconds()
            run_key = f"{sched['id']}:{today_date_str} {sched_time}"

            if run_key in self.schedule_last_run:
                continue

            # If delayed by more than 5 minutes (e.g. PC was asleep)
            if diff_sec > 300:
                self.schedule_last_run[run_key] = True
                continue

            # If within execution window (0 <= diff_sec <= 60)
            if 0 <= diff_sec <= 60:
                self.schedule_last_run[run_key] = True
                self._execute_schedule(sched)

    def _execute_schedule(self, sched: dict):
        target_type = sched.get('target_type')
        target_id = sched.get('target_id')
        action = sched.get('action')

        target_name = ""
        try:
            if target_type == 'scene':
                scene = self.get_scene(target_id)
                target_name = scene.get('name', 'Scene')
                self.scene_action(target_id, action)
            elif target_type == 'pad':
                target_name = self.get_pad_name(target_id)
                is_group = any(g['id'] == target_id for g in self.config.get('groups', []))
                if is_group:
                    self.group_action(target_id, action)
                else:
                    if action == 'start':
                        self.start(target_id)
                    else:
                        self.stop(target_id)

            # Record schedule alert if notification is enabled
            notif_cfg = self.config.get('notifications', {})
            if notif_cfg.get('schedule', True):
                act_str = '시작' if action == 'start' else '종료'
                self.record_alert(
                    pad_id=target_id,
                    pad_name=target_name,
                    kind='schedule_run',
                    message=f"예약 실행: '{target_name}' {act_str}"
                )
        except Exception as err:
            self.record_alert(
                pad_id=target_id,
                pad_name=target_name or target_id,
                kind='schedule_failed',
                message=f"예약 실행 실패 ({target_name}): {err}"
            )
