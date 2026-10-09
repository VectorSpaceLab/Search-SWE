"""Offline checks for a relocated skill; no Docker build or paid API calls."""

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

    def scaffold(self, name, *args):
        return subprocess.run(
            [sys.executable, str(self.skill / "scripts/scaffold_task.py"),
             name, "--repo-root", str(self.repo), *args],
            cwd=self.root, capture_output=True, text=True,
        )

    def test_all_mode_hardware_pairs_and_fail_closed_entrypoint(self):
        for mode, kind in (("implementation", "create"), ("optimization", "optimize")):
            for hardware, tag, gpus in (("cpu", "cpu-py3.12-1.0.0", 0),
                                       ("gpu", "gpu-cu13.0-py3.12-1.0.0", 1)):
                with self.subTest(mode=mode, hardware=hardware):
                    name = f"task-{mode}-{hardware}"
                    result = self.scaffold(name, "--mode", mode, "--hardware", hardware)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    task = self.repo / "tasks" / name
                    raw = (task / "raw-instruction.md").read_text()
                    instruction = (task / "instruction.md").read_text()
                    self.assertTrue(raw.strip())
                    self.assertTrue(instruction.strip())
                    self.assertNotEqual(raw, instruction)
                    config = tomllib.loads((task / "task.toml").read_text())
                    self.assertEqual(config["metadata"]["task_type"], kind)
                    self.assertEqual(config["environment"]["gpus"], gpus)
                    self.assertEqual(config["verifier"]["environment_mode"], "separate")
                    for phase in ("environment", "tests"):
                        self.assertEqual((task / phase / "Dockerfile").read_text().splitlines()[0],
                                         f"FROM docker.io/hanhainebula/search-swe-base:{tag}")
                        overlay = (task / phase / "docker-compose.yaml").read_text()
                        self.assertEqual("driver: nvidia" in overlay, bool(gpus))
                    script = task / "tests/test.sh"
                    self.assertTrue(script.read_bytes().startswith(b"#!/usr/bin/env bash\n"))
                    subprocess.run(["bash", "-n", str(script)], check=True)
                    # Redirect only the log directory into the temporary workspace.
                    log = task / "test-log"
                    local = task / "local-test.sh"
                    local.write_text(script.read_text().replace(
                        "reward_dir=/logs/verifier", f"reward_dir={shlex.quote(str(log))}"))
                    local.chmod(0o755)
                    failed = subprocess.run([str(local)], capture_output=True, text=True)
                    self.assertEqual(failed.returncode, 1)
                    self.assertEqual(float((log / "reward.txt").read_text()), 0)

    def test_existing_paths_and_invalid_mode_are_rejected(self):
        self.assertEqual(self.scaffold("task-new").returncode, 0)
        marker = self.repo / "tasks/task-new/keep.txt"
        marker.write_text("keep")
        self.assertNotEqual(self.scaffold("task-new").returncode, 0)
        self.assertEqual(marker.read_text(), "keep")
        link = self.repo / "tasks/task-link"
        target = self.root / "absent"
        link.symlink_to(target)
        self.assertNotEqual(self.scaffold("task-link").returncode, 0)
        self.assertFalse(target.exists())
        self.assertNotEqual(self.scaffold("task-other", "--mode", "repair").returncode, 0)
        self.assertFalse((self.repo / "tasks/task-other").exists())

    def test_submission_mode_reuses_namespace_and_explicit_name_suffix(self):
        self.assertNotEqual(self.scaffold("task-1-x-1", "--submission-first-name", "Alice").returncode, 0)
        for task_id in ("task-1-x-1", "task-1-x-2", "task-2-x-1"):
            mode = "optimization" if task_id.startswith("task-2") else "implementation"
            result = self.scaffold(task_id, "--submission-first-name", "Alice", "--author", "Alice Example",
                                   "--author", "Coauthor Example", "--mode", mode)
            self.assertEqual(result.returncode, 0, result.stderr)
            task = self.repo / "task-submissions/alice" / task_id.removeprefix("task-")
            config = tomllib.loads((task / "task.toml").read_text())
            self.assertEqual(config["task"]["name"], f"search-swe/{task_id}")
            self.assertEqual([a["name"] for a in config["task"]["authors"]], ["Alice Example", "Coauthor Example"])
        duplicate = self.scaffold("task-1-x-1", "--submission-first-name", "Alice",
                                  "--author", "Alice Example")
        self.assertNotEqual(duplicate.returncode, 0)
        result = self.scaffold("task-1-x-1", "--submission-first-name", "Alice-2",
                               "--author", "Another Alice")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.repo / "task-submissions/alice-2/1-x-1/task.toml").is_file())

    def test_submission_names_and_roots_are_safe(self):
        for name in ("../escape", "/absolute", "Élodie", "123"):
            self.assertNotEqual(self.scaffold("task-1-x-1", "--submission-first-name", name,
                                             "--author", "Real Author").returncode, 0)
        for task_id in ("task-1-x", "task-1-x-0", "task-1-6"):
            self.assertNotEqual(self.scaffold(task_id, "--submission-first-name", "Alice",
                                             "--author", "Alice").returncode, 0)
        (self.repo / "task-submissions").mkdir()
        (self.repo / "task-submissions/alice").symlink_to(self.root)
        self.assertNotEqual(self.scaffold("task-1-x-1", "--submission-first-name", "Alice",
                                         "--author", "Alice").returncode, 0)
        shutil.rmtree(self.repo / "task-submissions")
        (self.repo / "task-submissions").symlink_to(self.root)
        self.assertNotEqual(self.scaffold("task-1-x-1", "--submission-first-name", "Alice",
                                         "--author", "Alice").returncode, 0)
        shutil.rmtree(self.repo / "tasks")
        (self.repo / "tasks").symlink_to(self.root)
        self.assertNotEqual(self.scaffold("task-new").returncode, 0)

    def test_instruction_links_stay_inside_relocated_skill(self):
        # Markdown links are instructional dependencies; project paths in code
        # refer to the target checkout and intentionally remain external inputs.
        for document in self.skill.rglob("*.md"):
            for link in re.findall(r"\]\(([^)]+)\)", document.read_text()):
                if "://" in link or link.startswith("#"):
                    continue
                target = (document.parent / link.split("#")[0]).resolve()
                self.assertTrue(target.is_relative_to(self.skill), (document, link))
                self.assertTrue(target.is_file(), (document, link))

    def test_submission_category_matches_mode_independent_of_hardware(self):
        for category, mode in ((1, "implementation"), (2, "optimization")):
            wrong = "optimization" if category == 1 else "implementation"
            result = self.scaffold(f"task-{category}-x-1", "--submission-first-name", "Alice",
                                   "--author", "Alice", "--mode", wrong)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((self.repo / "task-submissions").exists())
        ordinal = 1
        for category, mode in ((1, "implementation"), (2, "optimization")):
            for hardware in ("cpu", "gpu"):
                result = self.scaffold(f"task-{category}-x-{ordinal}", "--submission-first-name", "Alice",
                                       "--author", "Alice", "--mode", mode, "--hardware", hardware)
                self.assertEqual(result.returncode, 0, result.stderr)
                ordinal += 1


if __name__ == "__main__":
    unittest.main()
