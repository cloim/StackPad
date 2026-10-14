"""Read-only home screen widget credentials. Only SHA-256 hashes of the tokens are persisted."""
import hashlib
import json
import secrets
import threading
import time
import uuid
from pathlib import Path

MAX_DEVICES = 20


class WidgetTokens:
    def __init__(self, data_dir):
        # Follows the engine's current data folder, so a storage move keeps the copied file in use.
        self.data_dir = data_dir
        self.lock = threading.RLock()
        try:
            records = json.loads(self.path.read_text('utf-8')) if self.path.exists() else []
            if not isinstance(records, list):
                raise ValueError('Invalid widget token records')
            self.records = [r for r in records if isinstance(r, dict) and isinstance(r.get('hash'), str) and len(r['hash']) == 64
                            and isinstance(r.get('id'), str) and isinstance(r.get('name'), str)]
            # Tokens from before phone pairing belong to no device, so nothing could ever disconnect them.
            if any('device' not in r for r in self.records):
                self.records = [r for r in self.records if 'device' in r]
                self.save()
        except (ValueError, OSError):
            self.records = []

    @property
    def path(self):
        return Path(self.data_dir()) / 'widget-tokens.json'

    def save(self):
        temporary = self.path.with_suffix('.tmp')
        temporary.write_text(json.dumps(self.records, ensure_ascii=False), 'utf-8')
        temporary.replace(self.path)

    def issue(self, name, device=None):
        token = secrets.token_urlsafe(32)
        record = {'id': uuid.uuid4().hex, 'name': name, 'hash': hashlib.sha256(token.encode()).hexdigest(),
                  'created_at': time.time(), 'last_used_at': None, 'device': device}
        with self.lock:
            if len(self.records) >= MAX_DEVICES:
                raise ValueError('위젯 연결 기기가 너무 많습니다. 사용하지 않는 기기를 해제해 주세요.')
            self.records.append(record)
            self.save()
        return record['id'], token

    def list(self):
        with self.lock:
            return [{key: r.get(key) for key in ('id', 'name', 'created_at', 'last_used_at')} for r in self.records]

    def revoke(self, token_id):
        with self.lock:
            remaining = [r for r in self.records if r['id'] != token_id]
            if len(remaining) == len(self.records):
                raise KeyError('위젯 연결을 찾지 못했습니다.')
            self.records = remaining
            self.save()

    def revoke_device(self, device):
        # A disconnected phone loses its widget connection too.
        with self.lock:
            remaining = [r for r in self.records if r.get('device') != device]
            if len(remaining) != len(self.records):
                self.records = remaining
                self.save()

    def verify(self, token):
        if not isinstance(token, str) or not token:
            return False
        digest = hashlib.sha256(token.encode()).hexdigest()
        with self.lock:
            record = next((r for r in self.records if secrets.compare_digest(r['hash'], digest)), None)
            if record is None:
                return False
            # Record use at most once a minute to avoid rewriting the file on every widget refresh burst.
            if not record['last_used_at'] or time.time() - record['last_used_at'] > 60:
                record['last_used_at'] = time.time()
                self.save()
            return True
