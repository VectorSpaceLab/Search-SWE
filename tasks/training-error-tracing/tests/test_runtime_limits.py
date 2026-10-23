"""Resource discovery for Docker's single-GPU count allocation; no GPU required."""

import os
from pathlib import Path
import unittest
from unittest.mock import patch

import grade


class RuntimeLimits(unittest.TestCase):
    def profile(self, gpu="GPU-assigned, NVIDIA A100-SXM4-40GB, 40960\n", **overrides):
        limits = {"cpu.max": "1600000 100000", "memory.max": str(64 * 1024**3),
                  "memory.swap.max": "0"}
        limits.update(overrides)
        with patch.object(Path, "read_text", lambda path: limits[path.name]), \
                patch.object(grade.subprocess, "check_output", return_value=gpu):
            return grade.verify_runtime_limits()

    def test_discovers_assigned_uuid_without_host_environment(self):
        with patch.dict(os.environ, {}, clear=True):
            result = self.profile()
        self.assertEqual(result["gpu_uuid"], "GPU-assigned")
        self.assertEqual(result["cpu_quota_cores"], 16)
        self.assertEqual(result["memory_max_bytes"], 64 * 1024**3)
        self.assertEqual(result["memory_swap_max_bytes"], 0)
        self.assertEqual(result["gpu_memory_total_mib"], 40960)

    def test_rejects_missing_multiple_or_malformed_gpu(self):
        for gpu in ("", "GPU-a, A100-SXM4-40GB, 40960\nGPU-b, A100-SXM4-40GB, 40960\n",
                    "GPU-a, A100-SXM4-40GB\n"):
            with self.subTest(gpu=gpu), self.assertRaisesRegex(ValueError, "exactly one physical GPU"):
                self.profile(gpu)

    def test_preserves_hardware_requirements(self):
        for gpu in ("MIG-a, A100-SXM4-40GB, 40960\n", "GPU-a, H100-80GB, 81920\n",
                    "GPU-a, A100-SXM4-40GB, 20000\n"):
            with self.subTest(gpu=gpu), self.assertRaisesRegex(ValueError, "physical A100 40GB"):
                self.profile(gpu)

    def test_preserves_cpu_memory_and_swap_limits(self):
        for limits in ({"cpu.max": "max 100000"}, {"cpu.max": "800000 100000"},
                       {"memory.max": "max"}, {"memory.max": str(32 * 1024**3)},
                       {"memory.swap.max": "1"}):
            with self.subTest(limits=limits), self.assertRaises(ValueError):
                self.profile(**limits)

    def test_gpu_probe_failure_is_an_infrastructure_error(self):
        limits = {"cpu.max": "1600000 100000", "memory.max": str(64 * 1024**3),
                  "memory.swap.max": "0"}
        with patch.object(Path, "read_text", lambda path: limits[path.name]), \
                patch.object(grade.subprocess, "check_output", side_effect=FileNotFoundError), \
                self.assertRaises(FileNotFoundError):
            grade.verify_runtime_limits()


if __name__ == "__main__":
    unittest.main()
