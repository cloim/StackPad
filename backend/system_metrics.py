"""Recent utilization of the host running the StackPad engine."""
import ctypes
from ctypes import wintypes
import os
import threading
import time
from collections import defaultdict, deque

import psutil


class _CounterValue(ctypes.Structure):
    # The native value union is formatted as a double for this query.
    _fields_ = [('status', wintypes.DWORD), ('value', ctypes.c_double)]


class _CounterItem(ctypes.Structure):
    _fields_ = [('name', wintypes.LPWSTR), ('reading', _CounterValue)]


class _WindowsGPU:
    def __init__(self):
        self.pdh = ctypes.WinDLL('pdh.dll')
        self.pdh.PdhGetFormattedCounterArrayW.restype = wintypes.DWORD
        self.query = wintypes.HANDLE()
        self.counter = wintypes.HANDLE()
        if self.pdh.PdhOpenQueryW(None, 0, ctypes.byref(self.query)):
            raise OSError('PdhOpenQueryW')
        if self.pdh.PdhAddEnglishCounterW(self.query, ctypes.c_wchar_p(r'\GPU Engine(*)\Utilization Percentage'), 0, ctypes.byref(self.counter)):
            self.close()
            raise OSError('PdhAddEnglishCounterW')

    def sample(self):
        if self.pdh.PdhCollectQueryData(self.query):
            return None
        size, count = wintypes.DWORD(), wintypes.DWORD()
        read = self.pdh.PdhGetFormattedCounterArrayW
        pdh_fmt_double, pdh_more_data = 0x200, 0x800007D2
        if read(self.counter, pdh_fmt_double, ctypes.byref(size), ctypes.byref(count), None) != pdh_more_data:
            return None
        data = ctypes.create_string_buffer(size.value)
        if read(self.counter, pdh_fmt_double, ctypes.byref(size), ctypes.byref(count), data):
            return None
        engines = defaultdict(float)
        for item in (_CounterItem * count.value).from_buffer(data):
            # Each instance is a process contribution to one engine. Match engines across PIDs.
            if item.reading.status in (0, 1) and item.name and item.name.startswith('pid_'):
                engine = item.name.split('_', 2)[-1].split('#', 1)[0]
                engines[engine] += max(0, item.reading.value)
        return round(min(100, max(engines.values())), 1) if engines else None

    def close(self):
        self.pdh.PdhCloseQuery(self.query)


class SystemMetrics:
    interval = 2

    def __init__(self):
        self.lock = threading.Lock()
        self.history = {metric: deque(maxlen=30) for metric in ('cpu', 'memory', 'gpu')}
        self.last_sample = None
        self.cpu_times = None
        self.gpu = None
        self.gpu_checked = False

    def snapshot(self):
        with self.lock:
            now = time.monotonic()
            if self.last_sample is None or now - self.last_sample >= self.interval:
                continuing = self.last_sample is not None and now - self.last_sample < self.interval * 3
                if not continuing:
                    for series in self.history.values():
                        series.clear()
                    self.cpu_times = None
                if not self.gpu_checked:
                    self.gpu_checked = True
                    if os.name == 'nt':
                        try:
                            self.gpu = _WindowsGPU()
                        except OSError:
                            pass  # Drivers without GPU performance counters still provide CPU and memory.
                times = psutil.cpu_times()._asdict()
                cpu = None
                if self.cpu_times is not None:
                    delta = {key: max(0, value - self.cpu_times[key]) for key, value in times.items()}
                    total = sum(delta.values()) - delta.get('guest', 0) - delta.get('guest_nice', 0)
                    if total > 0:
                        idle = delta['idle'] + delta.get('iowait', 0)
                        cpu = round(max(0, 100 * (total - idle) / total), 1)
                self.cpu_times = times
                self.history['cpu'].append(cpu)
                self.history['memory'].append(psutil.virtual_memory().percent)
                gpu = self.gpu.sample() if self.gpu else None
                self.history['gpu'].append(gpu if continuing else None)
                self.last_sample = now
            return {'interval': self.interval, **{metric: list(series) for metric, series in self.history.items()}}

    def close(self):
        with self.lock:
            if self.gpu:
                self.gpu.close()
                self.gpu = None
