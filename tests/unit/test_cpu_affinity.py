import copy
import os
from pathlib import Path
import unittest
import tempfile
from unittest.mock import patch

import yaml

from harbor.models.task.config import TaskConfig
from harbor.models.trial.paths import TrialPaths
from scripts.evaluation.cpu_affinity import (
    normalize_compose_cpu_quota, parse_cpu_set, select_compose_cpus, validate_cpu_set,
)
from scripts.evaluation.harbor_environments import DockerEnvironment, GpuDocker, PhaseScopedDocker


class CpuAffinityTests(unittest.TestCase):
    def test_harbor_integer_cpu_ids_are_normalized_before_validation(self):
        with patch.object(DockerEnvironment, "__init__", return_value=None):
            for value, expected in ((0, "0"), (8, "8"), ("8", "8"), ("8-9", "8-9"), (None, None)):
                with self.subTest(value=value):
                    self.assertEqual(GpuDocker(cpu_set=value).cpu_set, expected)
            for value in (-1, True, False, 1.0, [1], "", "1,,2"):
                with self.subTest(value=value), self.assertRaises(ValueError):
                    GpuDocker(cpu_set=value)

    def test_count_and_host_affinity_are_enforced(self):
        with patch("os.sched_getaffinity", return_value={2, 3, 8, 9}):
            self.assertEqual(validate_cpu_set("8-9,2-3", 4), "2,3,8,9")
            for value in ("0-3", "2-3", "9-2", "2,,3", "2-999999999"):
                with self.subTest(value=value), self.assertRaises(ValueError):
                    validate_cpu_set(value, 4)
        self.assertEqual(validate_cpu_set("1000-1001", 2, check_host=False), "1000,1001")

    def test_all_task_services_keep_every_other_resource_and_mount(self):
        root = Path(__file__).resolve().parents[2]
        for path in (root / "tasks").glob("*/*/docker-compose.yaml"):
            with self.subTest(path=path):
                document = yaml.safe_load(path.read_text())
                original = copy.deepcopy(document)
                selected = select_compose_cpus(document, "2,3")
                for name, service in selected["services"].items():
                    self.assertEqual(service.pop("cpuset"), "2,3")
                    expected = copy.deepcopy(original["services"][name])
                    expected.pop("cpuset", None)
                    self.assertEqual(service, expected)
                self.assertEqual(document, original)

    def test_only_equivalent_main_cpu_quota_is_normalized(self):
        source = {"services": {"main": {"cpu_period": 100000, "cpu_quota": 800000,
                                         "mem_limit": "32g", "volumes": ["./data:/data:ro"]},
                               "helper": {"cpu_period": 50000, "cpu_quota": 25000}}}
        before = copy.deepcopy(source)
        selected = normalize_compose_cpu_quota(source, 8)
        self.assertEqual(selected["services"]["main"],
                         {"cpus": 8, "mem_limit": "32g", "volumes": ["./data:/data:ro"]})
        self.assertEqual(selected["services"]["helper"], source["services"]["helper"])
        self.assertEqual(source, before)
        self.assertEqual(normalize_compose_cpu_quota(source, None), source)
        self.assertEqual(normalize_compose_cpu_quota(selected, 8), selected)
        for fields in ({"cpu_period": 50000, "cpu_quota": 400000},
                       {"cpu_period": 100000, "cpu_quota": 400000},
                       {"cpu_period": 100000}, {"cpu_quota": 800000},
                       {"cpu_period": True, "cpu_quota": 8},
                       {"cpu_period": 100000, "cpu_quota": -1},
                       {"cpu_period": 100000, "cpu_quota": 800000, "cpus": 4}):
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                normalize_compose_cpu_quota({"services": {"main": fields}}, 8)

    def test_all_task_phase_copies_preserve_budgets_with_or_without_cpu_selection(self):
        root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as directory:
            for path in (root / "tasks").glob("*/*/docker-compose.yaml"):
                before = path.read_bytes()
                original = yaml.safe_load(before)
                for cls in (GpuDocker, PhaseScopedDocker):
                    for cpu_set in (None, "0"):
                        with self.subTest(path=path, adapter=cls.__name__, cpu_set=cpu_set):
                            config = TaskConfig.model_validate_toml((path.parent.parent / "task.toml").read_text())
                            env = cls(environment_dir=path.parent, environment_name=path.parent.parent.name,
                                      session_id=f"fixture-{path.parent.name}", trial_paths=TrialPaths(Path(directory)),
                                      task_env_config=config.environment, override_gpus=0, cpu_set=cpu_set)
                            paths = env._docker_compose_paths
                            selected_path = next(p for p in paths if p == path or p.suffix == ".json")
                            selected = yaml.safe_load(selected_path.read_text())
                            expected = copy.deepcopy(original)
                            main = expected["services"]["main"]
                            if "cpu_period" in main:
                                self.assertEqual(main.pop("cpu_period"), 100000)
                                self.assertEqual(main.pop("cpu_quota"), config.environment.cpus * 100000)
                                main["cpus"] = config.environment.cpus
                            if cpu_set is not None:
                                for service in expected["services"].values():
                                    service["cpuset"] = cpu_set
                            self.assertEqual(selected, expected)
                            if expected == original:
                                self.assertEqual(selected_path, path)
                self.assertEqual(path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
