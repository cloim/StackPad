import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
import legacy


class LegacyMigrationTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.former = self.root / 'former'
        (self.former / 'logs').mkdir(parents=True)
        (self.former / 'config.json').write_text('{"services": []}', 'utf-8')
        (self.former / 'logs' / 'engine.log').write_text('log', 'utf-8')
        (self.former / 'cloudflare-access.json').write_text('{}', 'utf-8')
        self.target = self.root / 'stackpad'

    def test_copies_former_folder_and_keeps_original(self):
        self.assertEqual(legacy.migrate_data(self.target, [self.former]), self.former)
        self.assertEqual((self.target / 'config.json').read_text('utf-8'), '{"services": []}')
        self.assertTrue((self.target / 'logs' / 'engine.log').is_file())
        self.assertFalse((self.target / 'cloudflare-access.json').exists())
        self.assertTrue((self.former / 'config.json').is_file())

    def test_leaves_existing_target_untouched(self):
        self.target.mkdir()
        (self.target / 'config.json').write_text('{"current": true}', 'utf-8')
        self.assertIsNone(legacy.migrate_data(self.target, [self.former]))
        self.assertEqual((self.target / 'config.json').read_text('utf-8'), '{"current": true}')

    def test_skips_missing_sources(self):
        self.assertIsNone(legacy.migrate_data(self.target, [self.root / 'missing']))
        self.assertFalse(self.target.exists())

    def test_replaces_former_startup_link_for_desktop_app(self):
        startup = self.root / 'Microsoft/Windows/Start Menu/Programs/Startup'
        startup.mkdir(parents=True)
        link = startup / f'{legacy.FORMER_NAME}.lnk'
        link.write_bytes(b'')
        calls = []
        engine = SimpleNamespace(desktop_exe='C:/StackPad/StackPad.exe', autostart=calls.append)
        with patch.dict(os.environ, {'APPDATA': str(self.root)}):
            self.assertTrue(legacy.migrate_startup_link(engine))
        self.assertEqual(calls, [True])
        self.assertFalse(link.exists())

    def test_keeps_former_startup_link_without_desktop_app(self):
        startup = self.root / 'Microsoft/Windows/Start Menu/Programs/Startup'
        startup.mkdir(parents=True)
        link = startup / f'{legacy.FORMER_NAME}.lnk'
        link.write_bytes(b'')
        engine = SimpleNamespace(desktop_exe=None, autostart=lambda enabled: None)
        with patch.dict(os.environ, {'APPDATA': str(self.root)}):
            self.assertFalse(legacy.migrate_startup_link(engine))
        self.assertTrue(link.exists())


if __name__ == '__main__':
    unittest.main()
