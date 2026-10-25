"""Offline relocation and generation checks; no Docker builds or paid API calls."""

from pathlib import Path
import ast
import importlib.util
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import tomllib
import unittest

import yaml


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
        (self.repo / "scripts").mkdir()
        (self.repo / "scripts/harness_versions.py").write_text(
            'CODEX_VERSION="0.164.0"\nCLAUDE_CODE_VERSION="2.1.309"\nPI_VERSION="1.4.0"\n')

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
                for path in ("VALIDATION.md", "tests/grader.py", "tests/finalize_reward.py",
                             "tests/rewardkit_deepseek.py", "tests/jailbreak_judge/codex.toml",
                             "environment/.dockerignore", "tests/.dockerignore"):
                    self.assertTrue((task / path).is_file(), path)
                for path in task.rglob("*.py"):
                    ast.parse(path.read_text())
                gate_tests = subprocess.run(
                    [sys.executable, "-m", "unittest", "discover", "-s", str(task / "tests"),
                     "-p", "test_integrity_gate.py"], capture_output=True, text=True)
                self.assertEqual(gate_tests.returncode, 0, gate_tests.stderr)
                self.assertIn("/logs/agent/trajectory.json", config["artifacts"])
                self.assertEqual(config["verifier"]["allowed_hosts"], ["openrouter.ai"])
                self.assertIn("VERIFIER_OPENAI_API_KEY", config["verifier"]["env"]["OPENAI_API_KEY"])
                self.assertNotIn("env", config["environment"])
                failed, log = self.run_entrypoint(task)
                self.assertEqual(failed.returncode, 1)
                self.assertEqual(float((log / "reward.txt").read_text()), 0)
                self.assertFalse(json.loads((log / "judge-status.json").read_text())["measurement_valid"])

    def run_entrypoint(self, task, report=None, decision=1, judge_fails=False):
        """Exercise generated shell/finalizer in temporary paths; no UID/process control."""
        log = self.root / (task.name + "-logs")
        trajectory = self.root / "trajectory.json"
        trajectory.write_text('{"messages": []}\n')
        if report is not None:
            (task / "tests/grader.py").write_text(
                "from pathlib import Path\nimport json\n"
                f"p=Path({str(log)!r});p.mkdir(parents=True,exist_ok=True)\n"
                f"(p/'report.json').write_text(json.dumps({report!r}))\n")
        # The real backend is tested separately; this deterministic double emits
        # RewardKit's actual folder aggregate/detail schema and never calls APIs.
        aggregate = {"jailbreak_judge": decision}
        detail = {"jailbreak_judge": {"criteria": [{"name": "integrity", "raw": decision}],
                                     "judge_output": "offline structured result"}}
        (task / "tests/rewardkit_deepseek.py").write_text(
            "from pathlib import Path\nimport json,os,sys\n"
            "if os.environ.get('OFFLINE_JUDGE_FAIL')=='1':raise SystemExit(78)\n"
            "p=Path(sys.argv[sys.argv.index('--output')+1])\n"
            f"p.write_text(json.dumps({aggregate!r}))\n"
            f"d={detail!r}\n"
            "(p.parent/'reward-details.json').write_text(json.dumps(d))\n")
        script = (task / "tests/test.sh").read_text()
        script = script.replace("/logs/verifier", str(log))
        script = script.replace("/logs/agent/trajectory.json", str(trajectory))
        script = script.replace("/tests", str(task / "tests"))
        script = script.replace("/opt/conda/bin/python", shlex.quote(sys.executable))
        script = script.replace("install -d -o root -g root -m 0700", "mkdir -p")
        script = script.replace("pkill -TERM -u submission", "true").replace("pkill -KILL -u submission", "true")
        local = task / "offline-entrypoint.sh"
        local.write_text(script)
        env = {"PATH": os.environ["PATH"], "OPENAI_BASE_URL": "https://openrouter.ai/api/v1",
               "OPENAI_API_KEY": "offline-placeholder", "OFFLINE_JUDGE_FAIL": str(int(judge_fails))}
        return subprocess.run(["bash", str(local)], capture_output=True, text=True, env=env, timeout=20), log

    def test_resources_pins_and_budget_propagate(self):
        # Change the target pin to prove generation uses the target, not the
        # installed skill's original version or execution of a Python module.
        pins = self.repo / "scripts/harness_versions.py"
        pins.write_text('CODEX_VERSION="9.8.7"\nCLAUDE_CODE_VERSION="8.7.6"\nPI_VERSION="7.6.5"\n'
                        'raise RuntimeError("must not execute target code")\n')
        result = self.scaffold("custom-search", "--hardware", "gpu", "--cpus", "16",
                               "--memory-mb", "16384", "--storage-mb", "51200",
                               "--agent-timeout-sec", "21600", "--grader-timeout-sec", "9000",
                               "--judge-timeout-sec", "3600", "--title", "Custom Search")
        self.assertEqual(result.returncode, 0, result.stderr)
        task = self.repo / "tasks/custom-search"
        config = tomllib.loads((task / "task.toml").read_text())
        self.assertEqual(config["agent"]["timeout_sec"], 21600)
        self.assertEqual(config["verifier"]["timeout_sec"], 9000 + 3600 + 300 + 600)
        judge = tomllib.loads((task / "tests/jailbreak_judge/codex.toml").read_text())
        self.assertEqual(judge["judge"]["timeout"], 3600)
        for phase in ("environment", "tests"):
            main = yaml.safe_load((task / phase / "docker-compose.yaml").read_text())["services"]["main"]
            self.assertEqual(main["cpus"], config["environment"]["cpus"])
            self.assertEqual(main["mem_limit"], "16384m")
            self.assertEqual(main["mem_limit"], main["memswap_limit"])
            self.assertEqual(main["deploy"]["resources"]["limits"]["memory"], main["mem_limit"])
            self.assertEqual(main["deploy"]["resources"]["reservations"]["devices"][0]["count"], 1)
        self.assertIn("CODEX_VERSION=9.8.7", (task / "environment/Dockerfile").read_text())
        self.assertIn("CLAUDE_CODE_VERSION=8.7.6", (task / "environment/Dockerfile").read_text())
        self.assertIn("PI_VERSION=7.6.5", (task / "environment/Dockerfile").read_text())
        self.assertIn('CODEX_VERSION = "9.8.7"', (task / "tests/rewardkit_deepseek.py").read_text())
        self.assertIn("REWARDKIT_CODEX_VERSION=9.8.7", (task / "tests/Dockerfile").read_text())
        readme = (task / "README.md").read_text()
        self.assertEqual(readme.splitlines()[0], "# Custom Search")
        self.assertEqual((task / "raw-instruction.md").read_text().splitlines()[0], "# Custom Search")
        self.assertIn("Alice Example", readme)
        self.assertIn("16384 MiB", readme)
        self.assertEqual(re.findall(r"^## (.+)$", readme, re.M),
                         ["Task Metadata", "Change Log", "Difficulty Explanation", "Verification Explanation", "References"])

    def test_entrypoint_preserves_scores_and_reports_unavailable_judge(self):
        for label, metric, decision, judge_fails, exit_code in [
                ("accepted", .75, 1, False, 0), ("zero", 0., 1, False, 0),
                ("rejected", .75, 0, False, 0), ("unavailable", .75, 1, True, 1)]:
            with self.subTest(label=label):
                self.assertEqual(self.scaffold(label + "-search").returncode, 0)
                task = self.repo / "tasks" / (label + "-search")
                result, log = self.run_entrypoint(task, {"status": "ok", "valid": True, "reward": metric},
                                                  decision, judge_fails)
                self.assertEqual(result.returncode, exit_code, result.stderr)
                reward = json.loads((log / "reward.json").read_text())["reward"]
                self.assertEqual(reward, metric if decision and not judge_fails else 0.)
                self.assertEqual(float((log / "reward.txt").read_text()), reward)
                health = json.loads((log / "judge-status.json").read_text())
                self.assertEqual(health["measurement_valid"], not judge_fails)
                self.assertTrue((log / "grader.stdout.log").exists())
                self.assertIn("finalizer end status=", (log / "stages.log").read_text())

    def test_finalizer_rejects_malformed_and_inconsistent_audits(self):
        self.assertEqual(self.scaffold("gates-search").returncode, 0)
        path = self.repo / "tasks/gates-search/tests/finalize_reward.py"
        spec = importlib.util.spec_from_file_location("generated_finalizer", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        good = {"status": "ok", "valid": True, "reward": .5}
        def details(raw=1, value=1):
            return {"jailbreak_judge": {"criteria": [{"name": "integrity", "raw": raw, "value": value}],
                                       "judge_output": "parsed answer"}}
        for raw in (1, True, "yes"):
            result, health = module.combine(good, {"jailbreak_judge": 1}, details(raw), "0", "0", True)
            self.assertEqual(result["reward"], .5)
            self.assertTrue(health["measurement_valid"])
        for detail in ({}, details(None), details(.5), details(1, 0), details(float("nan"))):
            result, health = module.combine(good, {"jailbreak_judge": 1}, detail, "0", "0", True)
            self.assertEqual(result["reward"], 0.)
            self.assertFalse(health["measurement_valid"])
        for aggregate in ("yes", .5, float("nan"), None):
            _, health = module.combine(good, {"jailbreak_judge": aggregate}, details(), "0", "0", True)
            self.assertFalse(health["measurement_valid"])
        for primary, pstatus, jstatus, present in [
                (good, "124", "0", True), (good, "0", "124", True), (good, "0", "0", False),
                ({"status": "ok", "valid": True, "reward": float("nan")}, "0", "0", True),
                ({"status": "infrastructure_error", "valid": False, "reward": 0.}, "0", "0", True)]:
            _, health = module.combine(primary, {"jailbreak_judge": 1}, details(), pstatus, jstatus, present)
            self.assertFalse(health["measurement_valid"])
        result, health = module.combine({"status": "submission_failed", "valid": False, "reward": 0.},
                                        {"jailbreak_judge": 1}, details(), "0", "0", True)
        self.assertEqual(result["reward"], 0.)
        self.assertTrue(health["measurement_valid"])

    def test_primary_timeout_preserves_diagnostics_and_zero_reward(self):
        self.assertEqual(self.scaffold("timeout-search", "--grader-timeout-sec", "1").returncode, 0)
        task = self.repo / "tasks/timeout-search"
        (task / "tests/grader.py").write_text(
            'import time\nprint("primary started",flush=True)\ntime.sleep(3)\n')
        result, log = self.run_entrypoint(task)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(float((log / "reward.txt").read_text()), 0.)
        self.assertIn("primary started", (log / "grader.stdout.log").read_text())
        health = json.loads((log / "judge-status.json").read_text())
        self.assertEqual(health["primary_status"], "124")
        self.assertFalse(health["measurement_valid"])

    def test_invalid_pins_and_resource_values_leave_no_package(self):
        for flag in ("--cpus", "--memory-mb", "--storage-mb", "--agent-timeout-sec",
                     "--grader-timeout-sec", "--judge-timeout-sec"):
            self.assertNotEqual(self.scaffold("invalid-search", flag, "0").returncode, 0)
        (self.repo / "scripts/harness_versions.py").unlink()
        self.assertNotEqual(self.scaffold("invalid-search").returncode, 0)
        self.assertFalse((self.repo / "tasks/invalid-search").exists())

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
