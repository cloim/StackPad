"""Switch managed data directories while retaining live process log sources."""
import copy
import json
import logging
import shutil
import sys
import tempfile
import threading
from pathlib import Path


def resolve_data_dir(bootstrap):
    bootstrap = Path(bootstrap).resolve()
    pointer = bootstrap / 'storage-location.json'
    if not pointer.exists():
        return bootstrap
    data = json.loads(pointer.read_text('utf-8'))
    path = Path(data['path'])
    if not path.is_absolute() or not path.is_dir() or not (path / 'config.json').is_file():
        raise ValueError('설정과 로그 저장 폴더를 확인해 주세요.')
    return path.resolve()


class StorageLocation:
    def __init__(self, engine, sessions, pointer):
        self.engine = engine
        self.sessions = sessions
        self.pointer = Path(pointer)
        self.selection_lock = threading.Lock()

    def change(self, folder):
        target = Path(folder)
        if not target.is_absolute() or not target.is_dir():
            raise ValueError('존재하는 폴더의 전체 경로를 선택해 주세요.')
        target = target.resolve()
        engine = self.engine
        with engine.lock, self.sessions.lock:
            source = engine.data_dir.resolve()
            if target == source:
                return str(source)
            if target.is_relative_to(source) or source.is_relative_to(target):
                raise ValueError('현재 저장 폴더와 겹치지 않는 별도의 빈 폴더를 선택해 주세요.')
            if any(target.iterdir()):
                raise ValueError('기존 파일을 보존할 수 있도록 빈 폴더를 선택해 주세요.')
            old_output = sys.stderr
            new_output = None
            try:
                with tempfile.TemporaryFile(dir=target):
                    pass
                shutil.copytree(source, target, dirs_exist_ok=True, ignore=shutil.ignore_patterns('storage-location.json', '*.tmp'))
                moved = copy.deepcopy(engine.config)
                for service in moved['services']:
                    if service.get('kind', 'local') == 'local' and engine.owned(service):
                        service['runtime']['log_source'] = service['runtime'].get('log_source') or str(engine.latest_service_log(service['id']))
                new_config = target / 'config.json'
                temporary = new_config.with_suffix('.tmp')
                temporary.write_text(json.dumps(moved, ensure_ascii=False, indent=2), 'utf-8')
                temporary.replace(new_config)
                if getattr(old_output, 'name', None):
                    try:
                        old_path = Path(old_output.name)
                        if old_path.is_relative_to(source):
                            dest = target / old_path.relative_to(source)
                            dest.parent.mkdir(parents=True, exist_ok=True)
                            new_output = dest.open('a', encoding='utf-8', buffering=1)
                    except Exception:
                        pass
                pointer_temp = self.pointer.with_suffix('.tmp')
                pointer_temp.write_text(json.dumps({'path': str(target)}, ensure_ascii=False), 'utf-8')
                pointer_temp.replace(self.pointer)
            except OSError:
                if new_output is not None:
                    new_output.close()
                raise ValueError('저장 폴더를 변경하지 못했습니다. 기존 위치와 데이터는 유지됩니다. 쓰기 권한과 여유 공간을 확인한 뒤 빈 폴더를 선택해 주세요.') from None
            engine.data_dir = target
            engine.logs = target / 'logs'
            engine.path = new_config
            engine.config = moved
            self.sessions.path = target / 'sessions.json'
            # Packaged engines have a file-backed stderr. Test clients keep their own streams.
            if new_output is not None:
                for logger in [logging.getLogger(), *[v for v in logging.Logger.manager.loggerDict.values() if isinstance(v, logging.Logger)]]:
                    for handler in logger.handlers:
                        if isinstance(handler, logging.StreamHandler) and handler.stream is old_output:
                            handler.setStream(new_output)
                if sys.stdout is old_output:
                    sys.stdout = new_output
                sys.stderr = new_output
                old_output.close()
            return str(target)
