import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from engine import Engine, ServiceInput


class GitStateTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.engine = Engine(self.folder.name)
        self.addCleanup(self.engine.closed.set)
        self.repo = Path(self.folder.name) / 'repo'
        self.repo.mkdir()
        self.git('init')
        self.engine.add(ServiceInput(name='Git service', command='echo test', cwd=str(self.repo), slot=0))

    def git(self, *args):
        return subprocess.run(['git', '-C', str(self.repo), *args], check=True,
                              stdin=subprocess.DEVNULL, capture_output=True, creationflags=0x08000000)

    def state(self):
        self.engine.last_git_check = 0
        self.engine.refresh_git_states()
        return self.engine.snapshot()[0]['git_state']

    def test_untracked_staged_modified_and_clean(self):
        self.assertEqual(self.state(), 'clean')
        file = self.repo / 'example.txt'
        file.write_text('first', encoding='utf-8')
        self.assertEqual(self.state(), 'dirty')
        self.git('add', '.')
        self.assertEqual(self.state(), 'dirty')
        self.git('-c', 'user.name=Test', '-c', 'user.email=test@example.com', 'commit', '-m', 'initial')
        self.assertEqual(self.state(), 'clean')
        file.write_text('changed', encoding='utf-8')
        self.assertEqual(self.state(), 'dirty')
        self.git('restore', '.')
        self.assertEqual(self.state(), 'clean')
        file.unlink()
        self.assertEqual(self.state(), 'dirty')

    def test_non_repository_and_missing_git_are_unknown(self):
        self.engine.config['services'][0]['cwd'] = self.folder.name
        self.assertIsNone(self.state())
        with patch('engine.subprocess.run', side_effect=FileNotFoundError):
            self.assertIsNone(self.state())
        with patch('engine.subprocess.run', side_effect=subprocess.TimeoutExpired('git', 3)):
            self.assertIsNone(self.state())

    def test_shared_folder_is_checked_once_and_cached(self):
        self.engine.add(ServiceInput(name='Second', command='echo test', cwd=str(self.repo), slot=1))
        with patch('engine.subprocess.run', wraps=subprocess.run) as run:
            self.engine.refresh_git_states()
            self.engine.refresh_git_states()
            self.assertEqual(run.call_count, 1)


if __name__ == '__main__':
    unittest.main()
