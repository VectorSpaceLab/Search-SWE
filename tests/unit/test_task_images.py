import tomllib
from pathlib import Path
import unittest
import yaml


REPO = Path(__file__).resolve().parents[2]
CPU_IMAGE = "docker.io/hanhainebula/search-swe-base:cpu-py3.12-1.0.0"
GPU_IMAGE = "docker.io/hanhainebula/search-swe-base:gpu-cu13.0-py3.12-1.0.0"


class TaskImages(unittest.TestCase):
    def test_base_images_and_gpu_resources_match(self):
        tasks = sorted(path for path in (REPO / "tasks").glob("*") if path.is_dir())
        self.assertTrue(tasks)

        for task in tasks:
            with self.subTest(task=task.name):
                config = tomllib.loads((task / "task.toml").read_text())
                gpus = config["environment"].get("gpus")
                self.assertIn(gpus, (0, 1))
                gpu = gpus == 1

                expected_from = f"FROM {GPU_IMAGE if gpu else CPU_IMAGE}"
                for dockerfile in (task / "environment/Dockerfile", task / "tests/Dockerfile"):
                    self.assertEqual(dockerfile.read_text().splitlines()[0], expected_from)

                for compose in (
                    task / "environment/docker-compose.yaml",
                    task / "tests/docker-compose.yaml",
                ):
                    main = yaml.safe_load(compose.read_text())["services"]["main"]
                    devices = main.get("deploy", {}).get("resources", {}).get(
                        "reservations", {}
                    ).get("devices", [])
                    self.assertEqual(len(devices), int(gpu))
                    if gpu:
                        device = devices[0]
                        self.assertEqual(device["driver"], "nvidia")
                        self.assertIn("gpu", device["capabilities"])
                        if "device_ids" in device:
                            self.assertNotIn("count", device)
                            self.assertEqual(len(device["device_ids"]), 1)
                            self.assertIsInstance(device["device_ids"][0], str)
                            self.assertTrue(device["device_ids"][0].strip())
                        else:
                            self.assertEqual(device["count"], 1)


if __name__ == "__main__":
    unittest.main()
