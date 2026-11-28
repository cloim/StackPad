import sys
import unittest
from collections import namedtuple
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from system_metrics import SystemMetrics


class SystemMetricsTests(unittest.TestCase):
    def test_samples_are_shared_and_resume_without_old_history(self):
        metrics = SystemMetrics()
        metrics.gpu_checked = True
        gpu = metrics.gpu = Mock()
        gpu.sample.side_effect = [None, 0.0, 75.0, None]
        clock = [0]
        cpu_times = namedtuple('CpuTimes', 'user idle')
        with (
            patch('system_metrics.time.monotonic', side_effect=lambda: clock[0]),
            patch('system_metrics.psutil.cpu_times', side_effect=[cpu_times(50, 50), cpu_times(55, 65), cpu_times(60, 80), cpu_times(65, 95)]),
            patch('system_metrics.psutil.virtual_memory', return_value=SimpleNamespace(percent=40.0)),
        ):
            initial = metrics.snapshot()
            self.assertEqual(initial, {'interval': 2, 'cpu': [None], 'memory': [40.0], 'gpu': [None]})
            self.assertEqual(metrics.snapshot(), initial)
            clock[0] = 2
            self.assertEqual(metrics.snapshot()['cpu'], [None, 25.0])
            self.assertEqual(metrics.snapshot()['gpu'], [None, 0.0])
            clock[0] = 4
            self.assertEqual(metrics.snapshot()['gpu'], [None, 0.0, 75.0])
            clock[0] = 12
            self.assertEqual(metrics.snapshot(), initial)
        metrics.close()
        gpu.close.assert_called_once()
