import shutil
import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))

from engine import Engine, ServiceInput
from scenes import SceneInput


class TestScenes(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.engine = Engine(data_dir=self.temp_dir)

    def tearDown(self):
        self.engine.closed.set()
        self.engine.wake.set()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_scene_crud(self):
        # 1. Add scene
        s1 = self.engine.save_scene(None, SceneInput(name='Dev Env', color='#3b82f6', pad_ids=[]))
        self.assertEqual(s1['name'], 'Dev Env')
        self.assertEqual(s1['color'], '#3b82f6')
        scene_id = s1['id']

        # 2. Get scene
        s = self.engine.get_scene(scene_id)
        self.assertEqual(s['id'], scene_id)

        # 3. Update scene
        s2 = self.engine.save_scene(scene_id, SceneInput(name='Production Env', color='#ef4444', pad_ids=['pad-1', 'pad-2']))
        self.assertEqual(s2['name'], 'Production Env')
        self.assertEqual(s2['pad_ids'], ['pad-1', 'pad-2'])

        # 4. List scenes
        scenes = self.engine.get_scenes()
        self.assertEqual(len(scenes), 1)
        self.assertEqual(scenes[0]['name'], 'Production Env')

        # 5. Delete scene
        self.engine.delete_scene(scene_id)
        self.assertEqual(len(self.engine.get_scenes()), 0)
        with self.assertRaises(KeyError):
            self.engine.get_scene(scene_id)

    def test_clean_scenes_for_pad(self):
        # Create a service pad
        sid = self.engine.add(ServiceInput(
            name='Backend',
            command='python -c "import time; time.sleep(10)"',
            cwd=str(self.temp_dir),
            slot=0
        ))
        # Add scene with this pad
        scene = self.engine.save_scene(None, SceneInput(name='Dev', pad_ids=[sid, 'other-id']))
        self.assertIn(sid, scene['pad_ids'])

        # Delete service pad
        self.engine.delete(sid)
        updated_scene = self.engine.get_scene(scene['id'])
        self.assertNotIn(sid, updated_scene['pad_ids'])
        self.assertIn('other-id', updated_scene['pad_ids'])


if __name__ == '__main__':
    unittest.main()
