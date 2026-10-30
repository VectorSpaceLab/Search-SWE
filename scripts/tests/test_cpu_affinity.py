import copy
import os
from pathlib import Path
import unittest
from unittest.mock import patch

import yaml

from scripts.cpu_affinity import parse_cpu_set, select_compose_cpus, validate_cpu_set


class CpuAffinityTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
