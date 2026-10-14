import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
import main


class VersionTests(unittest.TestCase):
    def test_versions_match_package_json(self):
        version = json.loads((ROOT / 'package.json').read_text('utf-8'))['version']
        cargo = re.search(r'^version = "([^"]+)"', (ROOT / 'src-tauri/Cargo.toml').read_text('utf-8'), re.M).group(1)
        gradle = re.search(r'versionName "([^"]+)"', (ROOT / 'android/app/build.gradle').read_text('utf-8')).group(1)
        self.assertEqual((main.VERSION, cargo, gradle), (version, version, version))


if __name__ == '__main__':
    unittest.main()
