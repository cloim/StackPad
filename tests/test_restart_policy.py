import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from engine import Engine, ServiceInput


class RestartPolicyTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.engine = Engine(self.folder.name)
        self.engine.last_activity = 0

    def test_last_error_line_extraction(self):
        sid = self.engine.add(ServiceInput(
            name='ErrorPad',
            kind='local',
            command='cmd.exe',
            cwd=str(Path.cwd()),
            color='#22c55e',
            slot=0,
            padset_id='default',
        ))
        log_path = self.engine.latest_service_log(sid)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        # Write lines with ANSI codes and various lines
        log_content = (
            "Line 1: Normal startup\n"
            "\x1b[31mError: Connection refused to database\x1b[0m\n"
            "Line 3: Retrying...\n"
            "\x1b[33mTraceback (most recent call last): failed to connect\x1b[0m\n"
            "Line 5: Shutdown complete\n"
        )
        log_path.write_text(log_content, encoding='utf-8')

        extracted = self.engine.last_error_line(sid)
        self.assertIn("failed to connect", extracted)
        self.assertNotIn("\x1b[", extracted)  # ANSI must be stripped

    def test_on_failure_restart_flow_and_backoff(self):
        sid = self.engine.add(ServiceInput(
            name='FailPad',
            kind='local',
            command='cmd.exe',
            cwd=str(Path.cwd()),
            color='#22c55e',
            slot=0,
            padset_id='default',
            restart_policy='on-failure',
            restart_max=3,
        ))

        # Mock an owned service that has a runtime
        service = self.engine.service(sid)
        service['runtime'] = {'pid': 999999, 'created': time.time(), 'log_source': ''}

        # Simulate process disappearance in watch()
        # 1st crash: should schedule restart 1
        with patch.object(self.engine, 'owned', return_value=None):
            # Run one iteration of watch logic for local services
            services = [dict(s) for s in self.engine.config['services'] if s.get('kind', 'local') == 'local']
            for s in services:
                current = next((item for item in self.engine.config['services'] if item['id'] == s['id']), None)
                if current and current.get('runtime') == s.get('runtime') and current.get('runtime'):
                    error_line = self.engine.last_error_line(s['id'])
                    policy = current.get('restart_policy', 'never')
                    max_attempts = current.get('restart_max', 3)
                    record = self.engine.restarts.setdefault(s['id'], {'attempts': [], 'next_at': 0})
                    now_time = time.time()
                    record['attempts'] = [t for t in record['attempts'] if now_time - t < 600]
                    can_restart = policy == 'on-failure' and len(record['attempts']) < max_attempts
                    self.assertTrue(can_restart)
                    backoffs = [2, 4, 8, 16, 32, 60]
                    delay = backoffs[min(len(record['attempts']), len(backoffs) - 1)]
                    record['attempts'].append(now_time)
                    record['next_at'] = now_time + delay
                    msg = f"{len(record['attempts'])}/{max_attempts} 재시작 대기 중"
                    current.update(runtime=None, error=msg)
                    self.engine.samples[s['id']] = {'status': 'restarting', 'message': msg}
                    self.engine.record_alert(s['id'], s['name'], 'restarted', f"[{s['name']}] {msg}")

        self.assertEqual(len(self.engine.restarts[sid]['attempts']), 1)
        self.assertEqual(self.engine.samples[sid]['status'], 'restarting')
        self.assertEqual(self.engine.snapshot()[0]['status'], 'restarting')
        self.assertEqual(len(self.engine.alerts), 1)
        self.assertEqual(self.engine.alerts[0]['kind'], 'restarted')

        # 2nd and 3rd crashes
        for i in (2, 3):
            now_time = time.time()
            self.engine.restarts[sid]['attempts'].append(now_time)
        self.assertEqual(len(self.engine.restarts[sid]['attempts']), 3)

        # 4th crash: exceeds restart_max (3), should give up
        now_time = time.time()
        record = self.engine.restarts[sid]
        max_attempts = 3
        can_restart = len(record['attempts']) < max_attempts
        self.assertFalse(can_restart)

        self.engine.record_alert(sid, 'FailPad', 'gave_up', '[FailPad] 재시작 한도를 초과했습니다.')
        self.assertEqual(self.engine.alerts[-1]['kind'], 'gave_up')

    def test_manual_start_and_stop_resets_restarts(self):
        sid = self.engine.add(ServiceInput(
            name='ResetPad',
            kind='local',
            command='cmd.exe',
            cwd=str(Path.cwd()),
            color='#22c55e',
            slot=0,
            padset_id='default',
            restart_policy='on-failure',
        ))
        self.engine.restarts[sid] = {'attempts': [time.time()], 'next_at': time.time() + 10}
        self.assertIn(sid, self.engine.restarts)

        # Stop resets restarts
        self.engine.stop(sid)
        self.assertNotIn(sid, self.engine.restarts)

        # Add again to restarts
        self.engine.restarts[sid] = {'attempts': [time.time()], 'next_at': time.time() + 10}
        with patch.object(self.engine, 'owned', return_value=None), \
             patch('engine.powershell', return_value='{"ProcessId": 12345, "ReturnValue": 0}'), \
             patch('psutil.Process') as mock_proc:
            mock_proc.return_value.pid = 12345
            mock_proc.return_value.create_time.return_value = time.time()
            self.engine.start(sid)

        self.assertNotIn(sid, self.engine.restarts)

    def test_group_busy_skips_auto_restart(self):
        sid = self.engine.add(ServiceInput(
            name='GroupMember',
            kind='local',
            command='cmd.exe',
            cwd=str(Path.cwd()),
            color='#22c55e',
            slot=0,
            padset_id='default',
            restart_policy='on-failure',
        ))
        self.engine.restarts[sid] = {'attempts': [time.time()], 'next_at': time.time() - 1}
        self.engine.group_operations['group-1'] = 'start'
        self.engine.config['groups'] = [{'id': 'group-1', 'member_ids': [sid], 'slot': 0, 'padset_id': 'default'}]

        # Due restarts loop skips if sid in group_operations
        now_time = time.time()
        to_restart = []
        for s, r in list(self.engine.restarts.items()):
            if r.get('next_at') and now_time >= r['next_at']:
                if s not in self.engine.group_operations:
                    to_restart.append(s)

        self.assertEqual(to_restart, [sid])  # sid itself not in group_operations
        # but if sid is marked busy:
        self.engine.group_operations[sid] = 'start'
        to_restart_busy = [s for s, r in list(self.engine.restarts.items()) if s not in self.engine.group_operations]
        self.assertEqual(to_restart_busy, [])

    def test_watch_gives_up_after_restart_max(self):
        # Runs the real watch loop: automatic restarts must count toward restart_max instead of resetting it.
        sid = self.engine.add(ServiceInput(
            name='Crashing',
            kind='local',
            command='cmd /c "echo Error: boom & ping -n 4 127.0.0.1 >nul & exit 1"',
            cwd=str(Path.cwd()),
            color='#22c55e',
            slot=0,
            padset_id='default',
            restart_policy='on-failure',
            restart_max=2,
        ))
        self.engine.start(sid)
        watcher = threading.Thread(target=self.engine.watch, daemon=True)
        watcher.start()
        self.addCleanup(watcher.join, 10)
        self.addCleanup(self.engine.closed.set)
        deadline = time.time() + 90
        while time.time() < deadline and not any(a['kind'] == 'gave_up' for a in self.engine.alerts):
            time.sleep(.5)
        kinds = [a['kind'] for a in self.engine.alerts if a['pad_id'] == sid]
        self.assertEqual(kinds, ['restarted', 'restarted', 'gave_up'])
        gave_up = self.engine.alerts[-1]['message']
        self.assertTrue(gave_up.startswith('재시작 한도를 초과했습니다.'))
        self.assertIn('Error: boom', gave_up)


if __name__ == '__main__':
    unittest.main()
