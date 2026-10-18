import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from engine import Engine, ServiceInput


class LogsOffsetTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.engine = Engine(self.folder.name)
        self.service_id = self.engine.add(ServiceInput(
            name='LogsTest',
            kind='local',
            command='cmd.exe',
            cwd=str(Path.cwd()),
            color='#22c55e',
            slot=0,
            padset_id='default'
        ))
        self.log_path = self.engine.latest_service_log(self.service_id)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def test_initial_and_incremental_reads(self):
        # 1. Write initial text
        self.log_path.write_text('Line 1\nLine 2\n', encoding='utf-8', newline='')
        r1 = self.engine.logs_offset(self.service_id)
        self.assertTrue(r1['reset'])
        self.assertEqual(r1['text'], 'Line 1\nLine 2\n')
        self.assertEqual(r1['file'], self.log_path.name)
        self.assertEqual(r1['offset'], self.log_path.stat().st_size)

        # 2. Append new text and read incrementally
        with self.log_path.open('a', encoding='utf-8', newline='') as f:
            f.write('Line 3\n')

        r2 = self.engine.logs_offset(self.service_id, file=r1['file'], offset=r1['offset'])
        self.assertFalse(r2['reset'])
        self.assertEqual(r2['text'], 'Line 3\n')
        self.assertEqual(r2['offset'], self.log_path.stat().st_size)

        # 3. Read again without new data
        r3 = self.engine.logs_offset(self.service_id, file=r2['file'], offset=r2['offset'])
        self.assertFalse(r3['reset'])
        self.assertEqual(r3['text'], '')
        self.assertEqual(r3['offset'], self.log_path.stat().st_size)

    def test_file_rotation_resets(self):
        self.log_path.write_text('Old log content', encoding='utf-8')
        # Pass a different file name
        res = self.engine.logs_offset(self.service_id, file='other-log-file.log', offset=10)
        self.assertTrue(res['reset'])
        self.assertEqual(res['file'], self.log_path.name)
        self.assertEqual(res['text'], 'Old log content')

    def test_file_truncation_resets(self):
        self.log_path.write_text('A' * 1000, encoding='utf-8')
        r1 = self.engine.logs_offset(self.service_id)
        self.assertEqual(r1['offset'], 1000)

        # Truncate file to shorter length
        self.log_path.write_text('B' * 100, encoding='utf-8')
        r2 = self.engine.logs_offset(self.service_id, file=r1['file'], offset=1000)
        self.assertTrue(r2['reset'])
        self.assertEqual(r2['text'], 'B' * 100)
        self.assertEqual(r2['offset'], 100)

    def test_utf8_boundary_handling(self):
        # Korean character '가' is 3 bytes in UTF-8: b'\xea\xb0\x80'
        # Write prefix + multi-byte char
        prefix = b'Hello '
        korean_char = '한글테스트'.encode('utf-8')
        self.log_path.write_bytes(prefix + korean_char[:2])  # Incomplete UTF-8 sequence at end

        r1 = self.engine.logs_offset(self.service_id)
        # Should decode up to 'Hello ', stopping before the incomplete 2 bytes
        self.assertEqual(r1['text'], 'Hello ')
        self.assertEqual(r1['offset'], len(prefix))

        # Complete the UTF-8 sequence
        with self.log_path.open('ab') as f:
            f.write(korean_char[2:])

        r2 = self.engine.logs_offset(self.service_id, file=r1['file'], offset=r1['offset'])
        self.assertFalse(r2['reset'])
        self.assertEqual(r2['text'], '한글테스트')
        self.assertEqual(r2['offset'], len(prefix) + len(korean_char))

    def test_max_chunk_size_256kb(self):
        # Create 300KB of data
        large_chunk = b'X' * (300 * 1024)
        self.log_path.write_bytes(large_chunk)

        # Incremental read from offset 0
        r = self.engine.logs_offset(self.service_id, file=self.log_path.name, offset=0)
        self.assertFalse(r['reset'])
        self.assertEqual(len(r['text']), 256 * 1024)
        self.assertEqual(r['offset'], 256 * 1024)


if __name__ == '__main__':
    unittest.main()
