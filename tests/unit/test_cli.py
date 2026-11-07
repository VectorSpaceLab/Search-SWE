import argparse
from contextlib import contextmanager, redirect_stdout, redirect_stderr
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
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from search_swe import __version__
from search_swe.cli import main, parser, configure_run
from search_swe.configuration import Setting, read_env, save_env, check_config_destination, saved_setting, resolve_setting
from search_swe.repository import discover, find_repo
from search_swe.resources import Pool
from search_swe.runner import doctor, run_batch


class CliTests(unittest.TestCase):
    def test_native_atif_mismatch_stops_before_asset_estimates_or_downloads(self):
        (self.root / "scripts/evaluation/native_agents.py").touch()
        task = self.root / "tasks/first-search/task.toml"
        task.write_text('artifacts=["/logs/agent/trajectory.json"]\n' + task.read_text())
        with patch("search_swe.runner.asset_plan", side_effect=AssertionError("assets prepared")), \
                redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()) as error:
            self.assertEqual(main(["run", "first-search", "--repo", str(self.root), "--agent", "aider",
                                   "--provider", "native", "--model", "openai/gpt-4o", "--yes"]), 1)
        self.assertIn("requires an ATIF", error.getvalue())
        self.assertFalse((self.root / ".env").exists())

    def test_incompatible_checkout_fails_before_prompts_or_writes(self):
        for version in ("0.2.2", "0.4.0"):
            (self.root / "pyproject.toml").write_text(f'[project]\nname="search-swe"\nversion="{version}"\n')
            with patch("search_swe.wizard.select_setting", side_effect=AssertionError("prompted")), \
                    redirect_stderr(io.StringIO()) as error:
                self.assertEqual(main(["configure", "--repo", str(self.root), "--agent", "pi",
                                       "--provider", "direct", "--model", "google/gemini-2.5-flash", "--yes"]), 1)
            self.assertIn("needs a 0.3.x checkout", error.getvalue())
            self.assertFalse((self.root / ".env").exists())

    def test_compatible_patch_checkout_is_accepted(self):
        from search_swe.repository import check_compatibility
        (self.root / "pyproject.toml").write_text('[project]\nname="search-swe"\nversion="0.3.1"\n')
        check_compatibility(self.root)

    def test_new_pi_model_is_checked_before_credentials_and_backend_preflight(self):
        with patch("search_swe.model_catalog.load_models", return_value=({}, "unavailable")) as catalog, \
                patch("search_swe.cli.runner.preflight", side_effect=AssertionError("late check")), \
                redirect_stderr(io.StringIO()) as error:
            self.assertEqual(main(["configure", "--repo", str(self.root), "--agent", "pi", "--provider", "openrouter",
                                   "--model", "vendor/new-model", "--offline", "--yes"]), 1)
        self.assertIn("compatible catalog metadata", error.getvalue())
        catalog.assert_called_once_with(offline=True, refresh=False)
        self.assertFalse((self.root / ".env").exists())

    def test_insufficient_asset_space_stops_before_probes_or_downloads(self):
        plan = {"task_bytes": 100, "task_additional_bytes": 100, "cache_path": "/fixture/cache",
                "cache_additional_bytes": 100, "filesystems": [{"paths": ["/fixture"],
                "free_bytes": 150, "additional_bytes": 200}]}
        with patch("search_swe.runner.asset_plan", return_value=plan), \
                patch("search_swe.cli.verify_submission_keys", side_effect=AssertionError("probe")), \
                patch("search_swe.runner.run_batch", side_effect=AssertionError("download")), \
                redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()) as error:
            self.assertEqual(main(["run", "first-search", "--repo", str(self.root), "--yes"]), 1)
        self.assertIn("Insufficient asset storage", error.getvalue())

    def test_explicit_pi_model_refresh_is_honored_in_interactive_mode(self):
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()), \
                patch("search_swe.model_catalog.load_models", return_value=({}, "unavailable")) as catalog, \
                patch("sys.stdin.isatty", return_value=True), patch("sys.stdout.isatty", return_value=True):
            self.assertEqual(main(["configure", "--repo", str(self.root), "--agent", "pi", "--provider", "openrouter",
                                   "--model", "vendor/new-model", "--reasoning-effort", "default", "--refresh-models"]), 1)
        catalog.assert_called_once_with(offline=False, refresh=True)

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        (self.root / "pyproject.toml").write_text(f'[project]\nname="search-swe"\nversion="{__version__}"\n')
        (self.root / "scripts/evaluation").mkdir(parents=True)
        (self.root / "scripts/assets").mkdir()
        (self.root / "scripts/evaluation/run_task.py").touch()
        (self.root / "scripts/assets/download_assets.py").write_text(
            'import json,sys\n'
            'if "--plan" in sys.argv: print(json.dumps({"task_bytes":0,"task_additional_bytes":0,"cache_path":"/fixture/cache","cache_additional_bytes":0,"filesystems":[]}))\n'
            'else: print("fixture assets verified")\n')
        shutil.copyfile(ROOT / "scripts/assets/asset_space.py", self.root / "scripts/assets/asset_space.py")
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
        self.assertEqual(task.optional_variables(), {"JINA_API_KEY"})

    def test_model_compatibility_and_provider_keys(self):
        self.assertEqual(Setting().required(), {"AGENT_OPENROUTER_API_KEY"})
        for setting in (Setting("pi", "openrouter", "deepseek/deepseek-flash", "high"),
                        Setting("claude-code", "openrouter", "openai/gpt-6-luna", "max")):
            self.assertEqual(setting.validate().required(), {"AGENT_OPENROUTER_API_KEY"})
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
        (self.root / "scripts/evaluation/run_task.py").write_text(
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

    def test_cleanup_failure_stops_batch_before_reusing_resources(self):
        self.fake_launcher()
        first = self.tasks[0]
        (first.path / "tools").mkdir()
        (first.path / "tools/prepare_storage.py").touch()
        runtime = self.root / "retained-storage"

        @contextmanager
        def retained_storage(plan, env):
            env[plan.variable] = str(runtime)
            yield
            raise RuntimeError("Storage is still attached to a Docker container")

        storage = SimpleNamespace(
            StoragePlan=SimpleNamespace(discover=lambda *_: SimpleNamespace(variable="FIXTURE_STORAGE_ROOT")),
            prepared_storage=retained_storage,
        )
        output = self.root / "batch"
        pool = Pool({0, 1}, 8192, [])
        with patch("search_swe.runner.backend", return_value=storage), redirect_stdout(io.StringIO()), \
                self.assertRaisesRegex(RuntimeError, "batch stopped before reusing"):
            run_batch(self.root, self.tasks[:2], Setting(), dict(os.environ), pool, 1, output)
        report = json.loads((output / "run.json").read_text())
        self.assertEqual(report["status"], "failed")
        failed = report["tasks"][first.name]
        self.assertEqual(failed["status"], "cleanup-error")
        self.assertIn("still attached", failed["error"])
        self.assertEqual(failed["storage_root"], str(runtime))
        self.assertEqual(report["tasks"][self.tasks[1].name]["status"], "not-started")
        self.assertFalse((output / self.tasks[1].name).exists())
        self.assertEqual(len(pool.used), 1)

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
        def enter(setting, env, updates, **kwargs):
            updates["AGENT_OPENROUTER_API_KEY"] = env["AGENT_OPENROUTER_API_KEY"] = "fixture-entered-secret"
        with redirect_stdout(io.StringIO()) as output, \
                patch.dict(os.environ, {}, clear=True), patch("sys.stdin.isatty", return_value=True), \
                patch("sys.stdout.isatty", return_value=True), patch("search_swe.wizard.select_setting", return_value=Setting()), \
                patch("search_swe.wizard.configure_agent", side_effect=enter), \
                patch("search_swe.wizard.configure_task_services"), patch("search_swe.wizard.concurrency", return_value=1), \
                patch("search_swe.wizard.ask", return_value=False), patch("search_swe.runner.preflight"):
            self.assertEqual(configure_run(args, self.root), 0)
        self.assertEqual(path.read_text(), "# original\n")
        self.assertNotIn("fixture-entered-secret", output.getvalue())

    def test_configure_rejects_options_that_only_affect_runs(self):
        for option, value in (("--output", "batch"), ("--cpu-set", "0-3"),
                              ("--gpu-devices", "0"), ("--memory-gb", "8")):
            with self.subTest(option=option), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                parser().parse_args(["configure", option, value])
            self.assertIsNotNone(parser().parse_args(["run", option, value]))

    def test_invalid_resource_limits_fail_during_argument_parsing(self):
        for option, values in (("--memory-gb", ["nan", "inf", "-inf", "0", "-1"]),
                               ("--concurrency", ["0", "-1", "1.5"])):
            for value in values:
                with self.subTest(option=option, value=value), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                    parser().parse_args(["run", f"{option}={value}"])

    def test_scripted_model_changes_reset_effort_and_harness_changes_reset_route(self):
        def resolve(*flags):
            return resolve_setting(Setting(), parser().parse_args(["run", *flags]))
        self.assertEqual(resolve().effort, "max")
        self.assertEqual(resolve("--model", "vendor/new").effort, "default")
        self.assertEqual(resolve("--model", "vendor/new", "--reasoning-effort", "high").effort, "high")
        self.assertEqual(resolve("--agent", "pi"), Setting("pi", "direct", "deepseek/deepseek-flash", "default"))
        self.assertEqual(resolve("--agent", "claude-code").model, "anthropic/claude-opus-5.5")
        with self.assertRaisesRegex(ValueError, "model ID"):
            resolve("--provider", "direct")
        self.assertEqual(saved_setting({"AGENT_MODEL": "vendor/new"}).effort, "default")
        self.assertEqual(saved_setting({}), Setting())

    def test_configure_can_save_model_only_without_host_checks_or_launch(self):
        path = self.root / ".env"
        path.write_text("AGENT_OPENROUTER_API_KEY=fixture-secret\nSEARCH_SWE_CONCURRENCY=4\n")
        args = parser().parse_args(["configure", "--model", "vendor/new", "--yes"])
        with patch.dict(os.environ, {}, clear=True), redirect_stdout(io.StringIO()) as output, \
                patch("search_swe.runner.doctor") as host, patch("search_swe.runner.run_batch") as launch:
            self.assertEqual(configure_run(args, self.root), 0)
        values = read_env(path)
        self.assertEqual(values["SEARCH_SWE_CONCURRENCY"], "4")
        self.assertEqual(values["AGENT_REASONING_EFFORT"], "default")
        self.assertEqual(values["AGENT_OPENROUTER_API_KEY"], "fixture-secret")
        self.assertNotIn("fixture-secret", output.getvalue())
        self.assertNotIn('"resource_pool"', output.getvalue())
        host.assert_not_called()
        launch.assert_not_called()

    def test_configure_dry_run_never_invokes_backend_or_writes(self):
        args = parser().parse_args(["configure", "first-search", "--dry-run"])
        with patch.dict(os.environ, {}, clear=True), redirect_stdout(io.StringIO()), \
                patch("search_swe.cli.subprocess.run") as backend:
            self.assertEqual(configure_run(args, self.root), 0)
        backend.assert_not_called()
        self.assertFalse((self.root / ".env").exists())

    def test_unknown_task_fails_before_interactive_credentials(self):
        args = parser().parse_args(["configure", "misspelled-search"])
        with patch("search_swe.wizard.select_setting") as choose, \
                self.assertRaisesRegex(ValueError, "Unknown task"):
            configure_run(args, self.root)
        choose.assert_not_called()

    def test_existing_output_fails_before_credentials_or_assets(self):
        args = parser().parse_args(["run", "first-search", "--output", str(self.root)])
        with patch("search_swe.wizard.select_setting") as choose, \
                self.assertRaisesRegex(ValueError, "Output directory already exists"):
            configure_run(args, self.root)
        choose.assert_not_called()

    def test_wizard_reuses_saved_concurrency_and_configures_optional_tasks(self):
        from search_swe import wizard
        path = self.root / ".env"
        path.write_text("AGENT_OPENROUTER_API_KEY=fixture\nSEARCH_SWE_CONCURRENCY=4\n")
        args = parser().parse_args(["configure"])
        with redirect_stdout(io.StringIO()), patch.dict(os.environ, {}, clear=True), \
                patch("sys.stdin.isatty", return_value=True), patch("sys.stdout.isatty", return_value=True), \
                patch.object(wizard, "select_setting", return_value=Setting()), \
                patch.object(wizard, "configure_agent"), patch.object(wizard, "select_tasks", return_value=[]) as tasks, \
                patch.object(wizard, "concurrency", return_value=4) as concurrency, patch.object(wizard, "ask", return_value=True):
            self.assertEqual(configure_run(args, self.root), 0)
        self.assertFalse(tasks.call_args.kwargs["required"])
        concurrency.assert_called_once_with(None, default=4)
        self.assertEqual(read_env(path)["SEARCH_SWE_CONCURRENCY"], "4")
        with patch.object(wizard, "ask", side_effect=["Parallel", "4"]), \
                patch.object(wizard.questionary, "select") as select, patch.object(wizard.questionary, "text") as text:
            self.assertEqual(wizard.concurrency(None, default=4), 4)
        self.assertEqual(select.call_args.kwargs["default"], "Parallel")
        self.assertEqual(text.call_args.kwargs["default"], "4")

    def test_task_filter_can_retry_and_configuration_can_skip_tasks(self):
        from search_swe import wizard
        catalog = discover(self.root)
        with patch.object(wizard, "ask", side_effect=["no-match", "first", ["first-search"]]), \
                redirect_stdout(io.StringIO()) as output:
            self.assertEqual(wizard.select_tasks(catalog), [catalog["first-search"]])
        self.assertIn("Try another filter", output.getvalue())
        with patch.object(wizard, "ask", side_effect=["", []]), patch.object(wizard.questionary, "checkbox") as checkbox:
            self.assertEqual(wizard.select_tasks(catalog, required=False), [])
        self.assertTrue(checkbox.call_args.kwargs["validate"]([]))
        with patch.object(wizard, "ask") as ask:
            self.assertEqual(wizard.select_tasks({}, required=False), [])
            with self.assertRaisesRegex(ValueError, "No tasks found"):
                wizard.select_tasks({})
        ask.assert_not_called()

    def test_doctor_loads_selected_env_with_shell_precedence(self):
        path = self.root / "custom.env"
        path.write_text("DOCKER_HOST=unix:///custom.sock\nDOCKER_CONTEXT=from-file\n")
        with patch.dict(os.environ, {"DOCKER_CONTEXT": "from-shell"}, clear=True), \
                patch("search_swe.runner.doctor", return_value={}) as check, redirect_stdout(io.StringIO()):
            self.assertEqual(main(["doctor", "--repo", str(self.root), "--env-file", str(path)]), 0)
        self.assertEqual(check.call_args.kwargs["env"]["DOCKER_HOST"], "unix:///custom.sock")
        self.assertEqual(check.call_args.kwargs["env"]["DOCKER_CONTEXT"], "from-shell")

    def test_docker_failure_explains_next_step_without_echoing_configuration(self):
        context = subprocess.CompletedProcess([], 0, json.dumps([
            {"Endpoints": {"docker": {"Host": "unix:///var/run/docker.sock"}}}]))
        failure = subprocess.CalledProcessError(1, ["docker", "info"], stderr="fixture-private-value")
        with patch("search_swe.runner.shutil.which", return_value="fixture"), \
                patch("search_swe.runner.subprocess.run", side_effect=[context, failure]):
            with self.assertRaisesRegex(ValueError, "socket permissions") as error:
                doctor(self.root, env={})
        self.assertNotIn("fixture-private-value", str(error.exception))

    def test_repo_option_without_subcommand_starts_run(self):
        with patch("search_swe.cli.configure_run", return_value=0) as run:
            self.assertEqual(main(["--repo", str(self.root)]), 0)
        self.assertEqual(run.call_args.args[0].command, "run")


if __name__ == "__main__":
    unittest.main()
