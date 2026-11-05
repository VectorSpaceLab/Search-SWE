"""GPU portability and resource accounting without allocating a GPU."""
from pathlib import Path
import sys
from types import SimpleNamespace
import time
import unittest
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).parent / 'runtime'))
from model import FixedModel
from evaluate import Resources

class GpuResourceTests(unittest.TestCase):
    def test_loader_uses_supplied_device_without_a_capacity_assumption(self):
        cuda = SimpleNamespace(get_device_properties=Mock(side_effect=AssertionError('capacity queried')),
                               get_device_name=Mock(return_value='Test GPU'))
        torch = SimpleNamespace(set_num_threads=Mock(), manual_seed=Mock(), cuda=cuda, bfloat16=object())
        backend = Mock()
        backend.eval.return_value = backend
        transformers = SimpleNamespace(AutoTokenizer=SimpleNamespace(from_pretrained=Mock(return_value=object())),
            AutoModelForCausalLM=SimpleNamespace(from_pretrained=Mock(return_value=backend)))
        with patch.dict(sys.modules, {'torch': torch, 'transformers': transformers}):
            model = FixedModel({'cpu_threads': 8, 'attention': 'sdpa'}, '/supplied-model')
        self.assertIs(model.model, backend)
        cuda.get_device_properties.assert_not_called()
        self.assertEqual(transformers.AutoModelForCausalLM.from_pretrained.call_args.kwargs['device_map'], 'cuda:0')
        backend.eval.assert_called_once()

    def test_gpu_usage_is_recorded_and_host_memory_oom_still_fails(self):
        resources = object.__new__(Resources)
        used = 30 << 30
        resources.nvml = SimpleNamespace(nvmlDeviceGetMemoryInfo=lambda gpu: SimpleNamespace(used=used))
        resources.gpu = object()
        resources.peak_gpu = 0
        resources.last_disk = time.monotonic()
        resources.initial_oom = 0
        resources.oom_count = lambda: 0
        resources.check()
        self.assertEqual(resources.peak_gpu, used)
        resources.oom_count = lambda: 1
        with self.assertRaisesRegex(RuntimeError, 'aggregate memory OOM'):
            resources.check()

    def test_exactly_one_gpu_remains_required(self):
        for count in [0, 2]:
            nvml = SimpleNamespace(nvmlInit=lambda: None, nvmlDeviceGetCount=lambda: count)
            with self.subTest(count=count), patch.dict(sys.modules, {'pynvml': nvml}):
                with self.assertRaisesRegex(RuntimeError, 'Exactly one mapped GPU'):
                    Resources(Path('/submission'))

if __name__ == '__main__':
    unittest.main()
