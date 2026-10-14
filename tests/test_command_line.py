import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from engine import Engine, ServiceInput, port_open
from recommend import command_of


def free_port(family=socket.AF_INET, host='127.0.0.1'):
    with socket.socket(family) as probe:
        probe.bind((host, 0))
        return probe.getsockname()[1]


class CommandLine(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(prefix='stackpad-command-')
        self.addCleanup(self.folder.cleanup)
        self.engine = Engine(self.folder.name)
        self.ids = []

    def tearDown(self):
        for service_id in self.ids:
            self.engine.stop(service_id)

    def test_ipv6_only_listener_counts_as_open(self):
        port = free_port(socket.AF_INET6, '::1')
        server = subprocess.Popen([sys.executable, '-m', 'http.server', str(port), '--bind', '::1'], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=0x08000000)
        # The venv launcher runs the server as a child, so end the whole tree.
        self.addCleanup(server.wait, 10)
        self.addCleanup(subprocess.run, ['taskkill.exe', '/F', '/T', '/PID', str(server.pid)], stdin=subprocess.DEVNULL, capture_output=True)
        deadline = time.monotonic() + 15
        while not port_open(port):
            self.assertLess(time.monotonic(), deadline, 'IPv6 listener was not detected')
            time.sleep(0.2)
        values = ServiceInput(name='IPv6', command='echo duplicate', cwd=self.folder.name, port=port, slot=0)
        service_id = self.engine.add(values)
        with self.assertRaises(ValueError, msg='A second instance must not start on an IPv6 port in use'):
            self.engine.start(service_id)

    def test_percent_and_parenthesis_run_as_in_a_terminal(self):
        command = f'echo before) && "{sys.executable}" -u -c "import time; print(\'pct=%STACKPAD_UNSET%\', \'50%\'); time.sleep(30)"'
        service_id = self.engine.add(ServiceInput(name='Literal', command=command, cwd=self.folder.name, slot=0))
        self.ids.append(service_id)
        self.engine.start(service_id)
        log = self.engine.latest_service_log(service_id)
        deadline = time.monotonic() + 15
        while 'pct=' not in (log.read_text(encoding='utf-8', errors='replace') if log and log.exists() else ''):
            self.assertLess(time.monotonic(), deadline, 'Service output did not reach the log')
            time.sleep(0.2)
        text = log.read_text(encoding='utf-8', errors='replace')
        self.assertIn('before)', text)
        self.assertIn('pct=%STACKPAD_UNSET% 50%', text)
        self.assertTrue(self.engine.owned(self.engine.service(service_id)))

    def test_suggested_commands_keep_quotes_around_paths_with_spaces(self):
        shell = SimpleNamespace(name=lambda: 'cmd.exe', cmdline=lambda: ['cmd.exe', '/c', r'C:\Program Files\nodejs\node.exe', 'server.js'])
        self.assertEqual(command_of(shell), r'"C:\Program Files\nodejs\node.exe" server.js')
        quoted = SimpleNamespace(name=lambda: 'cmd.exe', cmdline=lambda: ['cmd.exe', '/d', '/s', '/c', 'npm run dev'])
        self.assertEqual(command_of(quoted), 'npm run dev')
        pwsh = SimpleNamespace(name=lambda: 'pwsh.exe', cmdline=lambda: ['pwsh.exe', '-Command', r"& 'C:\My Tools\run.ps1'"])
        self.assertEqual(command_of(pwsh), r"& 'C:\My Tools\run.ps1'")


if __name__ == '__main__':
    unittest.main()
