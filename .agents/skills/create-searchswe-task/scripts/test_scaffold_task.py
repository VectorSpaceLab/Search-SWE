"""Offline relocation and generation checks; no Docker builds or paid API calls."""

from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import tomllib
import unittest


class RelocatedSkill(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.skill = self.root / "standalone-skill"
        shutil.copytree(Path(__file__).resolve().parents[1], self.skill,
                        ignore=shutil.ignore_patterns("__pycache__"))
        self.repo = self.root / "project"
        (self.repo / "tasks").mkdir(parents=True)
        (self.repo / "docker").mkdir()
        (self.repo / "docker/README.md").write_text("# Project fixture\n")

    def scaffold(self, name, *args, authors=True):
        return subprocess.run(
            [sys.executable, str(self.skill / "scripts/scaffold_task.py"), name,
             "--repo-root", str(self.repo),
             *(["--author", "Alice Example"] if authors else []), *args],
            cwd=self.root, capture_output=True, text=True,
        )

    def test_cpu_gpu_generation_and_fail_closed_entrypoint(self):
        for hardware, tag, gpus in (("cpu", "cpu-py3.12-1.0.0", 0),
                                    ("gpu", "gpu-cu13.0-py3.12-1.0.0", 1)):
            with self.subTest(hardware=hardware):
                name = f"example-{hardware}-search"
                result = self.scaffold(name, "--hardware", hardware, "--author", "Coauthor Example")
                self.assertEqual(result.returncode, 0, result.stderr)
                task = self.repo / "tasks" / name
                self.assertNotEqual((task / "raw-instruction.md").read_text(),
                                    (task / "instruction.md").read_text())
                config = tomllib.loads((task / "task.toml").read_text())
                self.assertEqual(config["task"]["name"], f"search-swe/{name}")
                self.assertEqual([a["name"] for a in config["task"]["authors"]],
                                 ["Alice Example", "Coauthor Example"])
                self.assertNotIn("task_type", config["metadata"])
                self.assertEqual(config["environment"]["gpus"], gpus)
                self.assertEqual(config["verifier"]["environment_mode"], "separate")
                for phase in ("environment", "tests"):
                    self.assertEqual((task / phase / "Dockerfile").read_text().splitlines()[0],
                                     f"FROM docker.io/hanhainebula/search-swe-base:{tag}")
                    self.assertEqual("driver: nvidia" in (task / phase / "docker-compose.yaml").read_text(), bool(gpus))
                script = task / "tests/test.sh"
                subprocess.run(["bash", "-n", str(script)], check=True)
                log = task / "test-log"
                local = task / "local-test.sh"
                local.write_text(script.read_text().replace("reward_dir=/logs/verifier",
                                                           f"reward_dir={shlex.quote(str(log))}"))
                local.chmod(0o755)
                failed = subprocess.run([str(local)], capture_output=True, text=True)
                self.assertEqual(failed.returncode, 1)
                self.assertEqual(float((log / "reward.txt").read_text()), 0)

    def test_name_rules_authors_and_removed_options(self):
        for name in ("../escape", "/absolute", "Élodie", "123", "all", "task-1-1", "task-1-x-1",
                     "task-example", "Upper-Case", "one--two", "-prefix", "suffix-", "one-two-three-four-five-six"):
            self.assertNotEqual(self.scaffold(name).returncode, 0, name)
        self.assertNotEqual(self.scaffold("missing-author", authors=False).returncode, 0)
        self.assertNotEqual(self.scaffold("bad-author", "--author", "Search-SWE", authors=False).returncode, 0)
        self.assertNotEqual(self.scaffold("old-mode", "--mode", "implementation").returncode, 0)
        self.assertNotEqual(self.scaffold("old-namespace", "--submission-first-name", "Alice").returncode, 0)
        for name in ("retrieval", "one-two-three-four-five", "bm25-search"):
            self.assertEqual(self.scaffold(name).returncode, 0)

    def test_existing_task_files_are_preserved(self):
        self.assertEqual(self.scaffold("example-search").returncode, 0)
        marker = self.repo / "tasks/example-search/keep.txt"
        marker.write_text("keep")
        self.assertNotEqual(self.scaffold("example-search").returncode, 0)
        self.assertEqual(marker.read_text(), "keep")

    def test_symlink_roots_and_destinations_are_rejected(self):
        tasks = self.repo / "tasks"
        (tasks / "linked-search").symlink_to(self.root / "absent")
        self.assertNotEqual(self.scaffold("linked-search").returncode, 0)
        self.assertFalse((self.root / "absent").exists())
        shutil.rmtree(tasks)
        tasks.symlink_to(self.root)
        self.assertNotEqual(self.scaffold("example-search").returncode, 0)

    def test_instruction_links_stay_inside_relocated_skill(self):
        for document in self.skill.rglob("*.md"):
            for link in re.findall(r"\]\(([^)]+)\)", document.read_text()):
                if "://" in link or link.startswith("#"):
                    continue
                target = (document.parent / link.split("#")[0]).resolve()
                self.assertTrue(target.is_relative_to(self.skill), (document, link))
                self.assertTrue(target.is_file(), (document, link))


if __name__ == "__main__":
    unittest.main()
