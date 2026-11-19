"""Exercise single-device portability and unchanged host-resource limits."""
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).parent / 'runtime'))
import evaluate

class GpuResourceTests(unittest.TestCase):
    def nvml(self, count=1):
        return SimpleNamespace(nvmlInit=lambda: None, nvmlDeviceGetCount=lambda: count,
            nvmlDeviceGetHandleByIndex=lambda index: object(),
            nvmlDeviceGetName=Mock(side_effect=AssertionError('model queried')),
            nvmlDeviceGetMemoryInfo=Mock(side_effect=AssertionError('capacity queried')))

    def controls(self, cores=16, memory=32):
        return SimpleNamespace(cpu_quota=lambda: (cores * 100000, 100000),
                               memory_limit=lambda: memory << 30)

    def test_resource_setup_accepts_the_mapped_device(self):
        nvml = self.nvml()
        with patch.object(evaluate, 'pynvml', nvml), patch.object(evaluate, 'controller', return_value=self.controls()):
            resources = evaluate.Resources(0)
        nvml.nvmlDeviceGetName.assert_not_called()
        nvml.nvmlDeviceGetMemoryInfo.assert_not_called()
        self.assertEqual(resources.fixed_bytes, 0)

    def test_single_device_and_host_limits_are_retained(self):
        for count, cores, memory in [(0, 16, 32), (2, 16, 32), (1, 17, 32), (1, 16, 33)]:
            with self.subTest(count=count, cores=cores, memory=memory):
                with patch.object(evaluate, 'pynvml', self.nvml(count)), patch.object(evaluate, 'controller', return_value=self.controls(cores, memory)):
                    expected = evaluate.ResourceViolation if count != 1 else evaluate.CgroupError
                    with self.assertRaises(expected):
                        evaluate.Resources(0)

if __name__ == '__main__':
    unittest.main()
