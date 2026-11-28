import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
import tailscale

HOST = 'pc.tail1234.ts.net'
SAVED = f'https://{HOST}:48731'


class FakeTailscale:
    """Answers `tailscale status` and `serve status` from memory and records `serve --bg` calls."""
    def __init__(self, web=None, tcp=None, host=HOST, running=True):
        self.serve = {'Web': web or {}, 'TCP': tcp or {}}
        self.state = {'BackendState': 'Running' if running else 'Stopped', 'Self': {'DNSName': host + '.'}}
        self.added = []

    def run(self, *arguments, timeout=20):
        if arguments == ('status', '--json'):
            return json.dumps(self.state)
        if arguments == ('serve', 'status', '--json'):
            return json.dumps(self.serve)
        self.added.append(arguments)
        return ''


def proxy(target):
    return {'Handlers': {'/': {'Proxy': target}}}


class RestoreTests(unittest.TestCase):
    def restore(self, fake, saved=SAVED):
        with patch('tailscale._run', fake.run), patch('tailscale.executable', return_value='tailscale'):
            return tailscale.restore(48731, saved)

    def test_adds_the_missing_entry_on_the_saved_port(self):
        fake = FakeTailscale()
        self.assertTrue(self.restore(fake))
        self.assertEqual(fake.added, [('serve', '--bg', '--https=48731', 'http://127.0.0.1:48731')])

    def test_default_https_port(self):
        fake = FakeTailscale()
        self.assertTrue(self.restore(fake, f'https://{HOST}'))
        self.assertEqual(fake.added[0][2], '--https=443')

    def test_leaves_a_working_entry_alone(self):
        fake = FakeTailscale(web={f'{HOST}:48731': proxy('http://127.0.0.1:48731/')})
        self.assertFalse(self.restore(fake))
        self.assertEqual(fake.added, [])

    def test_nothing_saved_skips_tailscale(self):
        with patch('tailscale._run') as run:
            self.assertFalse(tailscale.restore(48731, None))
        run.assert_not_called()

    def test_refuses_a_port_another_service_holds(self):
        for fake in (FakeTailscale(web={f'{HOST}:48731': proxy('http://127.0.0.1:5173')}), FakeTailscale(tcp={'48731': {}})):
            with self.assertRaises(RuntimeError):
                self.restore(fake)
            self.assertEqual(fake.added, [])

    def test_refuses_when_the_machine_name_changed(self):
        fake = FakeTailscale(host='other.tail1234.ts.net')
        with self.assertRaises(RuntimeError):
            self.restore(fake)
        self.assertEqual(fake.added, [])

    def test_waits_for_tailscale_to_run(self):
        fake = FakeTailscale(running=False)
        with self.assertRaises(RuntimeError):
            self.restore(fake)
        self.assertEqual(fake.added, [])


if __name__ == '__main__':
    unittest.main()


class PadServeTests(unittest.TestCase):
    def test_reads_the_ports_of_a_serve_component(self):
        command = r'"C:\Program Files\Tailscale\tailscale.exe" serve --https=42435 http://127.0.0.1:41435'
        self.assertEqual(tailscale.serve_target(command), (42435, 41435))
        self.assertEqual(tailscale.serve_target('tailscale serve --https 8443 localhost:9000'), (8443, 9000))
        self.assertEqual(tailscale.serve_target('tailscale serve 3000'), (443, 3000))
        self.assertIsNone(tailscale.serve_target('npm run dev'))
        self.assertIsNone(tailscale.serve_target('tailscale serve --https=5173 off'))
        self.assertIsNone(tailscale.serve_target('tailscale serve --https=5173 http://192.168.0.5:5173'))

    def serve(self, fake, ports):
        with patch('tailscale._run', fake.run), patch('tailscale.executable', return_value='tailscale'):
            return tailscale.serve_local_ports(HOST, ports)

    def test_adds_missing_ports_and_skips_taken_ones(self):
        fake = FakeTailscale(web={f'{HOST}:8000': proxy('http://127.0.0.1:8000'), f'{HOST}:9000': proxy('http://127.0.0.1:1234')},
                             tcp={'8000': {'HTTPS': True}, '9000': {'HTTPS': True}, '7000': {'TCPForward': '127.0.0.1:22'}})
        fake.serve['Foreground'] = {'abc': {'Web': {f'{HOST}:5173': proxy('http://127.0.0.1:5173')}, 'TCP': {'5173': {'HTTPS': True}}}}
        self.assertEqual(self.serve(fake, [8000, 9000, 7000, 5173, 40001]), {8000, 5173, 40001})
        self.assertEqual(fake.added, [('serve', '--bg', '--https=40001', 'http://127.0.0.1:40001')])
