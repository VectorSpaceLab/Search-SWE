import argparse
from contextlib import redirect_stdout, redirect_stderr
import io
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from search_swe.cli import main, parser, configure_run
from search_swe.configuration import Setting, read_env, save_env, check_config_destination
from search_swe.repository import discover, find_repo
from search_swe.resources import Pool
from search_swe.runner import doctor, run_batch


class CliTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        (self.root / "scripts").mkdir()
        (self.root / "scripts/run_task.py").touch()
        (self.root / "scripts/download_assets.py").write_text('print("fixture assets verified")\n')
        for name in ("first-search", "second-search", "third-search"):
            task = self.root / "tasks" / name
            (task / "environment").mkdir(parents=True)
            (task / "environment/docker-compose.yaml").write_text('services:\n  main: {}\n')
            (task / "task.toml").write_text(
                '[environment]\ncpus=2\nmemory_mb=1024\nstorage_mb=1024\ngpus=0\n'
                'network_mode="public"\n[agent]\nnetwork_mode="public"\n'
                '[verifier]\nnetwork_mode="public"\n')
            (task / "assets.json").write_text('{"schema_version":1,"files":[]}')
        self.tasks = list(discover(self.root).values())

    def test_dotenv_is_literal_atomic_private_and_preserves_unrelated_lines(self):
        path = self.root / ".env"
        path.write_text('# keep this\nUNCHANGED="original"\nKEY=old\nKEY=duplicate\n')
        secret = "quote'backslash\\dollar$(never-run)${HOME}\nsecond line"
        save_env(path, {"KEY": secret, "AGENT_MODEL": "example/model"})
        self.assertEqual(read_env(path)["KEY"], secret)
        self.assertEqual(read_env(path)["UNCHANGED"], "original")
        self.assertIn('# keep this\nUNCHANGED="original"\n', path.read_text())
        self.assertEqual(path.read_text().count("KEY="), 1)
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

    def test_invalid_dotenv_and_symlink_are_not_overwritten(self):
        path = self.root / ".env"
        original = 'KEY="unclosed\n'
        path.write_text(original)
        with self.assertRaises(ValueError):
            save_env(path, {"KEY": "new"})
        self.assertEqual(path.read_text(), original)
        link = self.root / "linked.env"
        link.symlink_to(path)
        with self.assertRaises(ValueError):
            read_env(link)

    def test_repo_explicit_selection_is_not_silently_replaced(self):
        self.assertEqual(find_repo(self.root), self.root)
        with self.assertRaises(ValueError):
            find_repo(self.root / "missing")

    def test_credentials_cannot_be_saved_to_a_public_template_or_tracked_file(self):
        with self.assertRaises(ValueError):
            save_env(self.root / ".env.example", {"KEY": "fixture"})
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        (self.root / ".gitignore").write_text('.env\n.env.*\n!.env.example\n')
        check_config_destination(self.root, self.root / ".env")
        check_config_destination(self.root, self.root / ".env.tmp-fixture")
        for path in (self.root / ".env.example", self.root / "public.env"):
            with self.assertRaises(ValueError):
                check_config_destination(self.root, path)

    def test_fixed_judge_values_do_not_require_redundant_environment_keys(self):
        task = self.tasks[0]
        task.config["verifier"]["env"] = {
            "ANSWER_JUDGE_MODEL_NAME": "fixed/model", "ANSWER_JUDGE_BASE_URL": "https://example.org",
            "ANSWER_JUDGE_API_KEY": "${VERIFIER_OPENAI_API_KEY:-}", "JINA_API_KEY": "${JINA_API_KEY:-}"}
        self.assertEqual(task.required_variables(), {"VERIFIER_OPENAI_API_KEY"})
        self.assertEqual(task.optional_keys(), {"JINA_API_KEY"})

    def test_model_compatibility_and_provider_keys(self):
        self.assertEqual(Setting().required(), {"AGENT_OPENROUTER_API_KEY"})
        for setting in (Setting("pi", "openrouter", "deepseek/deepseek-flash", "high"),
                        Setting("claude-code", "openrouter", "openai/gpt-6-luna", "max")):
            with self.assertRaises(ValueError):
                setting.validate()
        self.assertEqual(Setting("pi", "direct", "zai/glm-5.3-flash", "high").validate().required(), {"ZAI_API_KEY"})

    def test_host_preflight_uses_resolved_docker_configuration(self):
        import platform
        local = subprocess.CompletedProcess([], 0, json.dumps([
            {"Endpoints": {"docker": {"Host": "unix:///var/run/docker.sock"}}}]))
        info = subprocess.CompletedProcess([], 0, json.dumps({
            "OSType": "linux", "KernelVersion": platform.release()}))
        env = {"DOCKER_HOST": "tcp://remote:2375"}
        with patch("search_swe.runner.shutil.which", return_value="fixture"), \
                patch("search_swe.runner.subprocess.run", return_value=local) as run:
            with self.assertRaisesRegex(ValueError, "local Unix-socket"):
                doctor(self.root, env=env)
            self.assertEqual(run.call_args.kwargs["env"], env)
        env["DOCKER_CONTEXT"] = "local-context"
        with patch("search_swe.runner.shutil.which", return_value="fixture"), \
                patch("search_swe.runner.subprocess.run", side_effect=[local, info, local]) as run:
            doctor(self.root, env=env)
            self.assertTrue(all(call.kwargs["env"] == env for call in run.call_args_list))

    def test_resource_allocations_are_disjoint_and_released(self):
        pool = Pool({0, 1, 2, 3}, 4096, ["GPU-one"])
        pool.validate(self.tasks, {})
        first = pool.acquire(self.tasks[0], {})
        second = pool.acquire(self.tasks[1], {})
        self.assertFalse(first.cpus & second.cpus)
        self.assertIsNone(pool.acquire(self.tasks[2], {}))
        pool.release(first)
        third = pool.acquire(self.tasks[2], {})
        self.assertEqual(third.cpus, first.cpus)
        with self.assertRaises(ValueError):
            Pool({0}, 4096, []).validate(self.tasks, {})
        with self.assertRaises(ValueError):
            Pool({0, 1}, 1024, []).validate(self.tasks, {})

    def test_gpu_tasks_cannot_share_one_device(self):
        from dataclasses import replace
        gpu_task = replace(self.tasks[0], gpus=1)
        pool = Pool({0, 1, 2, 3}, 8192, ["GPU-one"])
        first = pool.acquire(gpu_task, {})
        self.assertEqual(first.gpu, "GPU-one")
        self.assertIsNone(pool.acquire(gpu_task, {}))
        pool.release(first)
        self.assertIsNone(pool.acquire(gpu_task, {}, idle_gpus=set()))
        self.assertEqual(pool.acquire(gpu_task, {}).gpu, "GPU-one")

    def test_explicit_task_cpu_binding_is_respected(self):
        task = self.tasks[0]
        (task.path / "environment/docker-compose.yaml").write_text('services:\n  main:\n    cpuset: ${FIXED_CPUSET:-0-1}\n')
        pool = Pool({0, 1, 8, 9}, 8192, [])
        chosen = pool.acquire(task, {"FIXED_CPUSET": "8-9"})
        self.assertEqual(chosen.cpus, {8, 9})
        with self.assertRaises(ValueError):
            pool.validate([task], {"FIXED_CPUSET": "6-7"})

    def fake_launcher(self, *, fail=False, cancel=False):
        (self.root / "scripts/run_task.py").write_text(
            'import json, os, signal, sys, time\nfrom pathlib import Path\n'
            'if "--dry-run" in sys.argv or "--check" in sys.argv: raise SystemExit(0)\n'
            'task=sys.argv[sys.argv.index("--task")+1]\n'
            'cpus=sys.argv[sys.argv.index("--cpu-set")+1]\n'
            'output=Path(sys.argv[sys.argv.index("--output")+1]); output.mkdir()\n'
            'start=time.time(); time.sleep(0.4)\n'
            + ('os.kill(os.getppid(), signal.SIGINT); time.sleep(5)\n' if cancel else '')
            + '(output/"observed.json").write_text(json.dumps({"start":start,"end":time.time(),"cpus":cpus}))\n'
            + ('raise SystemExit(7 if task=="first-search" else 0)\n' if fail else ''))

    def test_parallel_batch_overlaps_and_queues_without_cpu_overlap(self):
        self.fake_launcher()
        output = self.root / "batch"
        pool = Pool({0, 1, 2, 3}, 8192, [])
        with redirect_stdout(io.StringIO()) as console:
            code = run_batch(self.root, self.tasks, Setting(), dict(os.environ), pool, 2, output)
        self.assertEqual(code, 0)
        self.assertNotIn("Waiting for an idle GPU", console.getvalue())
        records = [json.loads((output / task.name / "observed.json").read_text()) for task in self.tasks]
        self.assertLess(max(records[0]["start"], records[1]["start"]), min(records[0]["end"], records[1]["end"]))
        self.assertFalse(set(records[0]["cpus"].split(",")) & set(records[1]["cpus"].split(",")))
        self.assertGreaterEqual(records[2]["start"], min(records[0]["end"], records[1]["end"]))
        self.assertEqual(pool.used, [])

    def test_sequential_failure_is_recorded_and_other_tasks_continue(self):
        self.fake_launcher(fail=True)
        output = self.root / "batch"
        pool = Pool({0, 1}, 8192, [])
        env = dict(os.environ, AGENT_OPENROUTER_API_KEY="fixture-secret-not-for-logs")
        with redirect_stdout(io.StringIO()):
            code = run_batch(self.root, self.tasks[:2], Setting(), env, pool, 1, output)
        self.assertEqual(code, 1)
        raw = (output / "run.json").read_text()
        report = json.loads(raw)
        self.assertEqual(report["tasks"]["first-search"]["returncode"], 7)
        self.assertEqual(report["tasks"]["second-search"]["status"], "completed")
        self.assertNotIn("fixture-secret-not-for-logs", raw)
        first = json.loads((output / "first-search/observed.json").read_text())
        second = json.loads((output / "second-search/observed.json").read_text())
        self.assertGreaterEqual(second["start"], first["end"])

    def test_cancellation_releases_allocations_and_records_not_started_tasks(self):
        self.fake_launcher(cancel=True)
        output = self.root / "batch"
        pool = Pool({0, 1}, 8192, [])
        with redirect_stdout(io.StringIO()), self.assertRaises(KeyboardInterrupt):
            run_batch(self.root, self.tasks[:2], Setting(), dict(os.environ), pool, 1, output)
        self.assertEqual(pool.used, [])
        report = json.loads((output / "run.json").read_text())
        self.assertEqual(report["status"], "cancelled")
        self.assertEqual(report["tasks"]["second-search"]["status"], "not-started")

    def test_cli_dry_run_and_non_tty_never_write_env_or_start_work(self):
        self.fake_launcher()
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.dict(os.environ, {}, clear=True), redirect_stdout(stdout), redirect_stderr(stderr):
            self.assertEqual(main(["--repo", str(self.root), "run", "first-search", "--dry-run"]), 0)
            with patch("sys.stdin.isatty", return_value=False):
                self.assertEqual(main(["--repo", str(self.root), "run"]), 1)
        self.assertFalse((self.root / ".env").exists())
        self.assertFalse((self.root / "jobs").exists())
        self.assertIn("--yes", stderr.getvalue())

    def test_wizard_cancellation_does_not_save_entered_secret(self):
        path = self.root / ".env"
        path.write_text("# original\n")
        args = parser().parse_args(["configure", "first-search"])
        def enter(setting, env, updates):
            updates["AGENT_OPENROUTER_API_KEY"] = env["AGENT_OPENROUTER_API_KEY"] = "fixture-entered-secret"
        with redirect_stdout(io.StringIO()) as output, \
                patch.dict(os.environ, {}, clear=True), patch("sys.stdin.isatty", return_value=True), \
                patch("sys.stdout.isatty", return_value=True), patch("search_swe.wizard.select_setting", return_value=Setting()), \
                patch("search_swe.wizard.configure_agent", side_effect=enter), \
                patch("search_swe.wizard.configure_task_services"), patch("search_swe.wizard.concurrency", return_value=1), \
                patch("search_swe.wizard.ask", side_effect=[True, False]), patch("search_swe.runner.preflight"):
            self.assertEqual(configure_run(args, self.root), 0)
        self.assertEqual(path.read_text(), "# original\n")
        self.assertNotIn("fixture-entered-secret", output.getvalue())


if __name__ == "__main__":
    unittest.main()
