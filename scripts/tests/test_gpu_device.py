import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import PropertyMock, patch

import yaml

from scripts.gpu_device import resolve_gpu_device, select_compose_gpu, validate_gpu_device
from scripts.harbor_environments import DockerEnvironment, GpuDocker, PhaseScopedDocker


REPO = Path(__file__).resolve().parents[2]
GPU_A = "GPU-aaaaaaaa-1111-2222-3333-444444444444"
GPU_B = "GPU-bbbbbbbb-1111-2222-3333-444444444444"


class GpuSelection(unittest.TestCase):
    def test_single_index_and_uuid_only(self):
        for value in ("0", "2", GPU_A):
            self.assertEqual(validate_gpu_device(value), value)
        for value in ("", "all", "-1", "0,1", "GPU-short", " 0", "${GPU}"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_gpu_device(value)

    def test_resolves_host_index_and_uuid(self):
        inventory = SimpleNamespace(stdout=f"0, {GPU_A}\n2, {GPU_B}\n")
        with patch("scripts.gpu_device.subprocess.run", return_value=inventory):
            self.assertEqual(resolve_gpu_device("2"), GPU_B)
            self.assertEqual(resolve_gpu_device(GPU_A), GPU_A)
            with self.assertRaisesRegex(ValueError, "not present"):
                resolve_gpu_device("1")
        with patch("scripts.gpu_device.subprocess.run", side_effect=FileNotFoundError):
            with self.assertRaisesRegex(ValueError, "nvidia-smi"):
                resolve_gpu_device("0")

    def test_all_gpu_task_phases_only_replace_the_device_request(self):
        import tomllib
        for task in sorted((REPO / "tasks").glob("*/task.toml")):
            if not tomllib.loads(task.read_text())["environment"]["gpus"]:
                continue
            for phase in ("environment", "tests"):
                with self.subTest(task=task.parent.name, phase=phase):
                    source = yaml.safe_load((task.parent / phase / "docker-compose.yaml").read_text())
                    original = copy.deepcopy(source)
                    selected = select_compose_gpu(source, GPU_B)
                    request = selected["services"]["main"]["deploy"]["resources"]["reservations"]["devices"][0]
                    self.assertEqual(request["device_ids"], [GPU_B])
                    self.assertNotIn("count", request)
                    request.pop("device_ids")
                    request["count"] = 1
                    self.assertEqual(selected, original)
                    self.assertEqual(source, original)

    def test_rejects_missing_ambiguous_or_multigpu_requests(self):
        for devices in ([], [{"count": 2}], [{"driver": "nvidia", "count": 1,
                                              "capabilities": ["gpu"], "device_ids": [GPU_A]}]):
            source = {"services": {"main": {"deploy": {"resources": {"reservations": {"devices": devices}}}}}}
            with self.assertRaises(ValueError):
                select_compose_gpu(source, GPU_A)

    def test_phase_copies_are_independent_and_leave_source_intact(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for phase in ("environment", "tests"):
                env_dir = root / phase
                env_dir.mkdir()
                source = env_dir / "docker-compose.yaml"
                source.write_text((REPO / "tasks/code-embedding-finetuning" / phase / "docker-compose.yaml").read_text())
                before = source.read_bytes()
                for cls in (GpuDocker, PhaseScopedDocker):
                    for run, identity in (("one", GPU_A), ("two", GPU_B)):
                        env = object.__new__(cls)
                        env.environment_dir = env_dir
                        env.session_id = f"{run}-{phase}"
                        env.gpu_device = identity
                        env.trial_paths = SimpleNamespace(trial_dir=root / run)
                        env._gateway_overlay = root / "gateway.json"
                        with patch.object(DockerEnvironment, "_docker_compose_paths", new_callable=PropertyMock,
                                          return_value=[root / "base.yaml", source]):
                            paths = env._docker_compose_paths
                            selected = json.loads(paths[1].read_text())
                            self.assertEqual(selected["services"]["main"]["deploy"]["resources"]["reservations"]
                                             ["devices"][0]["device_ids"], [identity])
                            if cls is PhaseScopedDocker:
                                self.assertEqual(paths[-1], env._gateway_overlay)
                            env.gpu_device = None
                            self.assertEqual(env._docker_compose_paths[1], source)
                self.assertEqual(source.read_bytes(), before)

    def test_launcher_preview_and_cpu_rejection(self):
        with tempfile.NamedTemporaryFile() as env_file:
            env = {"PATH": os.environ["PATH"], "AGENT_OPENAI_BASE_URL": "https://api.example.org/v1"}
            def launch(task, *options):
                return subprocess.run(
                    [sys.executable, str(REPO / "scripts/run_task.py"), "--env-file", env_file.name,
                     "--task", task, "--model", "fixture", "--dry-run", *options],
                    env=env, capture_output=True, text=True,
                )
            selected = launch("code-embedding-finetuning", "--gpu-device", "2")
            self.assertEqual(selected.returncode, 0, selected.stderr)
            self.assertIn("gpu_device=2", selected.stdout)
            self.assertIn("PhaseScopedDocker", selected.stdout)
            self.assertIn("--override-gpus 0", selected.stdout)
            default = launch("code-embedding-finetuning")
            self.assertEqual(default.returncode, 0, default.stderr)
            self.assertNotIn("gpu_device=", default.stdout)
            cpu = launch("reasoning-query-rewriting", "--gpu-device", "0")
            self.assertNotEqual(cpu.returncode, 0)
            self.assertIn("single-GPU task", cpu.stderr)
            invalid = launch("code-embedding-finetuning", "--gpu-device", "0,1")
            self.assertNotEqual(invalid.returncode, 0)


if __name__ == "__main__":
    unittest.main()
