import tomllib
from pathlib import Path
import unittest


REPO = Path(__file__).resolve().parents[2]
CPU_IMAGE = "docker.io/hanhainebula/search-swe-base:cpu-py3.12-1.0.0"
GPU_IMAGE = "docker.io/hanhainebula/search-swe-base:gpu-cu13.0-py3.12-1.0.0"
GPU_TASKS = {"code-embedding-finetuning", "query-encoder-alignment"}


class TaskImages(unittest.TestCase):
    def test_base_images_and_gpu_resources_match(self):
        tasks = sorted(path for path in (REPO / "tasks").glob("*") if path.is_dir())
        self.assertTrue(tasks)
        configured_gpu_tasks = set()

        for task in tasks:
            with self.subTest(task=task.name):
                config = tomllib.loads((task / "task.toml").read_text())
                gpus = config["environment"].get("gpus")
                self.assertIn(gpus, (0, 1))
                gpu = gpus == 1
                if gpu:
                    configured_gpu_tasks.add(task.name)

                expected_from = f"FROM {GPU_IMAGE if gpu else CPU_IMAGE}"
                for dockerfile in (task / "environment/Dockerfile", task / "tests/Dockerfile"):
                    self.assertEqual(dockerfile.read_text().splitlines()[0], expected_from)

                for compose in (
                    task / "environment/docker-compose.yaml",
                    task / "tests/docker-compose.yaml",
                ):
                    text = compose.read_text()
                    self.assertEqual("driver: nvidia" in text, gpu)
                    self.assertEqual("count: 1" in text, gpu)

        self.assertEqual(configured_gpu_tasks, GPU_TASKS)


if __name__ == "__main__":
    unittest.main()
