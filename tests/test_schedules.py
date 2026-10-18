import datetime
import shutil
import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))

from engine import Engine, ServiceInput
from schedules import ScheduleInput


class TestSchedules(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.engine = Engine(data_dir=self.temp_dir)

    def tearDown(self):
        self.engine.closed.set()
        self.engine.wake.set()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_schedule_crud(self):
        # 1. Add schedule
        s1 = self.engine.save_schedule(None, ScheduleInput(
            target_type='pad',
            target_id='pad-1',
            action='start',
            time='09:00',
            days=[0, 1, 2, 3, 4]
        ))
        self.assertEqual(s1['target_type'], 'pad')
        self.assertEqual(s1['time'], '09:00')
        self.assertEqual(s1['days'], [0, 1, 2, 3, 4])
        self.assertTrue(s1['enabled'])
        sched_id = s1['id']

        # 2. Get schedule
        s = self.engine.get_schedule(sched_id)
        self.assertEqual(s['id'], sched_id)

        # 3. Toggle schedule
        toggled = self.engine.toggle_schedule(sched_id, False)
        self.assertFalse(toggled['enabled'])
        self.assertFalse(self.engine.get_schedule(sched_id)['enabled'])

        # 4. Delete schedule
        self.engine.delete_schedule(sched_id)
        self.assertEqual(len(self.engine.get_schedules()), 0)

    def test_check_schedules(self):
        # Create a service
        sid = self.engine.add(ServiceInput(
            name='TestService',
            command='python -c "import time; time.sleep(1)"',
            cwd=str(self.temp_dir),
            slot=0
        ))
        # Monday (weekday 0) at 09:00
        sched = self.engine.save_schedule(None, ScheduleInput(
            target_type='pad',
            target_id=sid,
            action='start',
            time='09:00',
            days=[0]
        ))

        # Simulation 1: Tuesday at 09:00 -> should not run
        tuesday_9am = datetime.datetime(2026, 10, 20, 9, 0, 0) # 2026-10-20 is Tuesday (weekday 1)
        self.engine.check_schedules(now=tuesday_9am)
        self.assertNotIn(f"{sched['id']}:2026-10-20 09:00", self.engine.schedule_last_run)

        # Simulation 2: Monday at 09:00:15 -> should run
        monday_9am = datetime.datetime(2026, 10, 19, 9, 0, 15) # 2026-10-19 is Monday (weekday 0)
        self.engine.check_schedules(now=monday_9am)
        self.assertIn(f"{sched['id']}:2026-10-19 09:00", self.engine.schedule_last_run)

        # Simulation 3: Monday at 09:00:30 (same minute) -> duplicate prevented
        monday_9am_again = datetime.datetime(2026, 10, 19, 9, 0, 30)
        self.engine.check_schedules(now=monday_9am_again)

        # Simulation 4: Monday delayed by 10 minutes (09:10) -> skipped
        monday_late = datetime.datetime(2026, 10, 26, 9, 10, 0)
        sched2 = self.engine.save_schedule(None, ScheduleInput(
            target_type='pad',
            target_id=sid,
            action='start',
            time='09:00',
            days=[0]
        ))
        self.engine.check_schedules(now=monday_late)
        self.assertTrue(self.engine.schedule_last_run.get(f"{sched2['id']}:2026-10-26 09:00"))


if __name__ == '__main__':
    unittest.main()
