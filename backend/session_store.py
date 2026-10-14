"""Persist only hashes of login credentials so logins survive engine restarts."""
import hashlib
import json
import threading
import time
from pathlib import Path

SESSION_TTL = 30 * 24 * 60 * 60
# Paired phones stay signed in until the owner disconnects them.
DEVICE_TTL = 365 * 24 * 60 * 60
MAX_SESSIONS = 200


def _digest(credential):
    return hashlib.sha256(credential.encode()).hexdigest()


def _valid(key, record):
    return (isinstance(key, str) and len(key) == 64 and all(char in '0123456789abcdef' for char in key)
            and isinstance(record, dict) and isinstance(record.get('expires'), (int, float)) and record['expires'] > time.time()
            and isinstance(record.get('email'), str) and record.get('kind') in ('browser', 'device'))


class SessionStore:
    def __init__(self, data_dir):
        self.path = Path(data_dir) / 'sessions.json'
        self.lock = threading.RLock()
        try:
            records = json.loads(self.path.read_text('utf-8')) if self.path.exists() else {}
            if not isinstance(records, dict):
                raise ValueError('Invalid session records')
            # Records without an account belong to the former password login and are dropped.
            self.records = {key: record for key, record in records.items() if _valid(key, record)}
        except (ValueError, OSError):
            self.records = {}

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix('.tmp')
        temporary.write_text(json.dumps(self.records, ensure_ascii=False), 'utf-8')
        temporary.replace(self.path)

    def __len__(self):
        with self.lock:
            return len(self.records)

    def create(self, credential, email, kind='browser', name=''):
        now = time.time()
        with self.lock:
            self.records = {key: record for key, record in self.records.items() if record['expires'] > now}
            if len(self.records) >= MAX_SESSIONS:
                # Drop the browser logins closest to expiry; paired devices are only removed by the owner.
                browsers = sorted((record['expires'], key) for key, record in self.records.items() if record['kind'] == 'browser')
                for _, key in browsers[:len(self.records) - MAX_SESSIONS + 1]:
                    self.records.pop(key)
            self.records[_digest(credential)] = {'expires': now + (DEVICE_TTL if kind == 'device' else SESSION_TTL), 'email': email,
                                                 'kind': kind, 'name': name, 'created': now}
            self.save()

    def get(self, credential):
        if not isinstance(credential, str) or not credential:
            return None
        with self.lock:
            record = self.records.get(_digest(credential))
            return dict(record) if record and record['expires'] > time.time() else None

    def pop(self, credential):
        if not isinstance(credential, str):
            return None
        with self.lock:
            value = self.records.pop(_digest(credential), None)
            self.save()
            return value

    def revoke_email(self, email):
        with self.lock:
            self.records = {key: record for key, record in self.records.items() if record['email'] != email}
            self.save()

    def devices(self):
        with self.lock:
            return [{'id': key[:16], 'name': record['name'], 'email': record['email'], 'created_at': record['created']}
                    for key, record in self.records.items() if record['kind'] == 'device' and record['expires'] > time.time()]

    def revoke_device(self, device_id):
        with self.lock:
            matches = [key for key, record in self.records.items() if record['kind'] == 'device' and key[:16] == device_id]
            if not matches:
                raise KeyError('연결된 기기를 찾을 수 없습니다.')
            for key in matches:
                self.records.pop(key)
            self.save()

    def device_id(self, credential):
        """The short id of a paired device session, or None for browser logins."""
        record = self.get(credential)
        return _digest(credential)[:16] if record and record['kind'] == 'device' else None
