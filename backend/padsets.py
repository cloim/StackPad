"""Each padset owns sixteen independent slots."""
import uuid
from i18n import system_text
from pydantic import BaseModel, ConfigDict, Field, field_validator


class PadsetInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1, max_length=40)

    @field_validator('name')
    @classmethod
    def clean(cls, value):
        value = value.strip()
        if not value or any(c in value for c in ('\x00', '\n', '\r')):
            raise ValueError('패드셋 이름을 한 줄로 입력해 주세요.')
        return value


class Padsets:
    def reorder_padsets(self, ids):
        with self.lock:
            previous = self.config['padsets']
            by_id = {s['id']: s for s in previous}
            if len(ids) != len(by_id) or len(set(ids)) != len(ids) or set(ids) != set(by_id):
                raise ValueError('현재 패드셋 전체를 한 번씩 지정해 주세요.')
            self.config['padsets'] = [by_id[sid] for sid in ids]
            try:
                self.save()
            except Exception:
                self.config['padsets'] = previous
                raise

    def init_padsets(self):
        changed = 'padsets' not in self.config and self.path.exists()
        self.config.setdefault('padsets', [{'id': 'default', 'name': system_text('기본')}])
        for pad in [*self.config['services'], *self.config.get('groups', [])]:
            if 'padset_id' not in pad:
                pad['padset_id'] = 'default'
                changed = True
        if changed:
            self.save()

    def padset(self, padset_id):
        for padset in self.config['padsets']:
            if padset['id'] == padset_id:
                return padset
        raise ValueError('패드셋을 선택해 주세요.')

    def save_padset(self, values, padset_id=None):
        with self.lock:
            if any(s['name'].casefold() == values.name.casefold() and s['id'] != padset_id for s in self.config['padsets']):
                raise ValueError('다른 패드셋 이름을 입력해 주세요.')
            previous = [dict(s) for s in self.config['padsets']]
            if padset_id:
                self.padset(padset_id)['name'] = values.name
            else:
                padset_id = uuid.uuid4().hex
                self.config['padsets'].append({'id': padset_id, 'name': values.name})
            try:
                self.save()
            except Exception:
                self.config['padsets'] = previous
                raise
            return padset_id

    def delete_padset(self, padset_id):
        with self.lock:
            self.padset(padset_id)
            if len(self.config['padsets']) == 1:
                raise ValueError('패드셋을 하나 이상 유지해 주세요.')
            if any(s['padset_id'] == padset_id for s in [*self.config['services'], *self.config.get('groups', [])]):
                raise ValueError('패드를 다른 셋으로 옮기거나 삭제한 다음 빈 패드셋을 삭제해 주세요.')
            previous = self.config['padsets']
            self.config['padsets'] = [s for s in previous if s['id'] != padset_id]
            try:
                self.save()
            except Exception:
                self.config['padsets'] = previous
                raise
