import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from scripts.task_storage import StoragePlan, prepared_storage, require_unused, run_command


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.task = self.root / "tasks/example-search"
        (self.task / "tools").mkdir(parents=True)
        (self.task / "environment").mkdir()
        (self.task / "environment/docker-compose.yaml").write_text(
            'services:\n  main:\n    cpuset: ${EXAMPLE_CPUSET:-80,81}\n'
            '    volumes: ["${EXAMPLE_STORAGE_ROOT:?Prepare storage}/agent:/app"]\n')
        # A real helper subprocess exercises the lifecycle without sudo, FUSE,
        # model calls or Docker. The production task scripts are smoke-tested
        # separately on a supported host.
        (self.task / "tools/prepare_storage.py").write_text(
            'import argparse, os\nfrom pathlib import Path\n'
            'p=argparse.ArgumentParser()\n'
            'p.add_argument("--runtime-root", type=Path)\np.add_argument("--run-id")\n'
            'p.add_argument("--unmount", action="store_true")\na=p.parse_args()\n'
            'assert "AGENT_OPENROUTER_API_KEY" not in os.environ\n'
            'assert "VERIFIER_OPENAI_API_KEY" not in os.environ\n'
            'r=a.runtime_root/a.run_id\n'
            'if a.unmount: (r/"unmounted").touch()\n'
            'else: r.mkdir(); (r/"prepared").touch()\n')
        self.bin = self.root / "bin"
        self.bin.mkdir()
        docker = self.bin / "docker"
        docker.write_text(f'#!{sys.executable}\n# No retained containers.\n')
        docker.chmod(0o755)
        self.plan = StoragePlan.discover(self.task, {"environment": {"cpus": 2}})

    def test_cpu_selection_uses_host_affinity_not_fixed_large_ids(self):
        env = {}
        with patch("os.sched_getaffinity", return_value={4, 6, 8}):
            self.plan.configure_cpus(env)
        self.assertEqual(env["EXAMPLE_CPUSET"], "4,6")

    def test_explicit_cpu_binding_is_preserved_and_validated(self):
        with patch("os.sched_getaffinity", return_value={4, 5, 8}):
            env = {"EXAMPLE_CPUSET": "4-5"}
            self.plan.configure_cpus(env)
            self.assertEqual(env["EXAMPLE_CPUSET"], "4-5")
            for value in ("0-1", "4", "4,5,8", "4,,5", "8-4", "4-9999999999"):
                with self.subTest(value=value), self.assertRaises(ValueError):
                    self.plan.configure_cpus({"EXAMPLE_CPUSET": value})

    def test_insufficient_cpus_fails_before_start(self):
        with patch("os.sched_getaffinity", return_value={3}), self.assertRaises(ValueError):
            self.plan.configure_cpus({})

    def test_other_tasks_need_no_storage_helper(self):
        (self.task / "tools/prepare_storage.py").unlink()
        self.assertIsNone(StoragePlan.discover(self.task, {}))

    def test_standard_entrypoint_prepares_passes_environment_and_cleans(self):
        if os.getuid() != 0 or len(os.sched_getaffinity(0)) < 2:
            self.skipTest("CLI fixture needs host root and two CPUs; sudo path is tested separately")
        scripts = Path(__file__).resolve().parents[1]
        shutil.copytree(scripts, self.root / "scripts", ignore=shutil.ignore_patterns("tests", "__pycache__"))
        (self.task / "task.toml").write_text(
            '[environment]\ncpus=2\ngpus=0\nnetwork_mode="public"\n'
            '[agent]\nnetwork_mode="public"\n[verifier]\nnetwork_mode="public"\n')
        (self.task / "assets.json").write_text('{"schema_version":1,"files":[]}')
        (self.bin / "docker").write_text(
            f'#!{sys.executable}\nimport json, platform, sys\n'
            'if "context" in sys.argv: print(json.dumps([{"Endpoints":{"docker":{"Host":"unix:///fixture"}}}]))\n'
            'elif "info" in sys.argv: print(json.dumps({"OSType":"linux","KernelVersion":platform.release()}))\n')
        observed = self.root / "harbor-observed.json"
        harbor = self.bin / "harbor"
        harbor.write_text(
            f'#!{sys.executable}\nimport json, os, sys\nfrom pathlib import Path\n'
            'assert "fixture-agent-secret" not in " ".join(sys.argv)\n'
            'assert os.environ["AGENT_OPENAI_API_KEY"] == "fixture-agent-secret"\n'
            'root=Path(os.environ["EXAMPLE_STORAGE_ROOT"])\n'
            'assert (root/"prepared").exists()\n'
            f'Path({str(observed)!r}).write_text(json.dumps({{"root":str(root),"cpus":os.environ["EXAMPLE_CPUSET"]}}))\n'
            'raise SystemExit(7)\n')
        harbor.chmod(0o755)
        env = {"PATH": str(self.bin) + os.pathsep + os.environ["PATH"],
               "HOME": str(self.root), "AGENT_OPENAI_BASE_URL": "https://agent.example/v1",
               "AGENT_OPENAI_API_KEY": "fixture-agent-secret"}
        command = [sys.executable, str(self.root / "scripts/run_task.py"),
                   "--task", "example-search", "--model", "fixture-model"]
        preview = subprocess.run([*command, "--dry-run"], env=env, capture_output=True, text=True, timeout=30)
        self.assertEqual(preview.returncode, 0, preview.stderr)
        self.assertFalse((self.root / "jobs").exists())
        result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 7, result.stderr)
        record = json.loads(observed.read_text())
        self.assertEqual(len(record["cpus"].split(",")), 2)
        self.assertTrue((Path(record["root"]) / "unmounted").exists())
        self.assertNotIn("fixture-agent-secret", result.stdout + result.stderr)

    def lifecycle(self, failure=False):
        host_env = {"PATH": str(self.bin) + os.pathsep + os.environ["PATH"],
                    "AGENT_OPENROUTER_API_KEY": "fixture-agent-secret",
                    "VERIFIER_OPENAI_API_KEY": "fixture-verifier-secret"}
        env = dict(os.environ) | host_env
        with patch.dict(os.environ, host_env), patch("os.getuid", return_value=0), \
                patch("os.sched_getaffinity", return_value={2, 3}), \
                patch("scripts.task_storage.check_host", return_value="unix:///fixture"):
            try:
                with prepared_storage(self.plan, env):
                    runtime = Path(env["EXAMPLE_STORAGE_ROOT"])
                    self.assertTrue((runtime / "prepared").exists())
                    self.assertFalse((runtime / "unmounted").exists())
                    self.assertEqual(env["EXAMPLE_CPUSET"], "2,3")
                    if failure:
                        raise ValueError("synthetic launch failure")
                    result = run_command([sys.executable, "-c", "raise SystemExit(7)"], env, self.root)
                    self.assertEqual(result, 7)
            except ValueError:
                if not failure:
                    raise
        self.assertTrue((runtime / "unmounted").exists())
        self.assertTrue((runtime / "prepared").exists())
        return runtime

    def test_nonzero_harbor_exit_cleans_storage_and_retains_evidence(self):
        first = self.lifecycle()
        second = self.lifecycle()
        self.assertNotEqual(first, second)

    def test_launch_exception_cleans_storage(self):
        self.lifecycle(failure=True)

    def test_sudo_is_authorized_once_and_helper_handles_cleanup(self):
        record = self.root / "sudo-calls.jsonl"
        sudo = self.bin / "sudo"
        sudo.write_text(
            f'#!{sys.executable}\nimport os, sys, json\n'
            f'with open({str(record)!r}, "a") as f: f.write(json.dumps(sys.argv[1:])+"\\n")\n'
            'if sys.argv[1:] != ["-v"]:\n'
            '    args=sys.argv[sys.argv.index("--")+1:]; os.execv(args[0], args)\n')
        sudo.chmod(0o755)
        env = dict(os.environ)
        with patch.dict(os.environ, {"PATH": str(self.bin) + os.pathsep + os.environ["PATH"]}), \
                patch("os.getuid", return_value=1234), \
                patch("os.sched_getaffinity", return_value={2, 3}), \
                patch("scripts.task_storage.check_host", return_value="unix:///fixture"):
            with prepared_storage(self.plan, env):
                runtime = Path(env["EXAMPLE_STORAGE_ROOT"])
        calls = [json.loads(line) for line in record.read_text().splitlines()]
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0], ["-v"])
        self.assertEqual(calls[1][0], "-n")
        self.assertTrue(calls[1][1].startswith("--preserve-env=http_proxy,"))
        self.assertTrue((runtime / "unmounted").exists())

    def test_busy_storage_is_retained_and_cleanup_failure_is_reported(self):
        (self.bin / "docker").write_text(
            f'#!{sys.executable}\nimport json, sys\nfrom pathlib import Path\n'
            'if "ps" in sys.argv: print("retained-container")\n'
            f'else: print(json.dumps([{{"Source":str(next(Path({str(self.root)!r}).glob("jobs/.task-storage/example-search/run-*"))/"agent")}}]))\n')
        env = dict(os.environ)
        with patch.dict(os.environ, {"PATH": str(self.bin) + os.pathsep + os.environ["PATH"]}), \
                patch("os.getuid", return_value=0), \
                patch("os.sched_getaffinity", return_value={2, 3}), \
                patch("scripts.task_storage.check_host", return_value="unix:///fixture"):
            with self.assertRaisesRegex(RuntimeError, "cleanup is incomplete"):
                with prepared_storage(self.plan, env):
                    runtime = Path(env["EXAMPLE_STORAGE_ROOT"])
        self.assertTrue((runtime / "prepared").exists())
        self.assertFalse((runtime / "unmounted").exists())

    def test_caller_managed_storage_is_not_unmounted(self):
        runtime = self.root / "existing"
        env = {"EXAMPLE_STORAGE_ROOT": str(runtime)}
        with patch("os.sched_getaffinity", return_value={2, 3}), \
                patch("scripts.task_storage.check_host", return_value="unix:///fixture"), \
                patch("scripts.task_storage.subprocess.Popen") as start:
            with prepared_storage(self.plan, env):
                self.assertEqual(env["EXAMPLE_STORAGE_ROOT"], str(runtime))
            start.assert_not_called()

    def test_cleanup_refuses_containers_that_reference_run_storage(self):
        runtime = self.root / "run"
        for source, busy in ((str(runtime / "agent/app"), True),
                             (str(runtime) + "-another/agent/app", False)):
            with self.subTest(source=source), patch("scripts.task_storage.docker_output", side_effect=[
                    "container-id\n", json.dumps([{"Source": source}]) + "\n"]):
                if busy:
                    with self.assertRaises(RuntimeError):
                        require_unused(runtime, "unix:///fixture")
                else:
                    require_unused(runtime, "unix:///fixture")

    def test_cleanup_preserves_storage_when_docker_cannot_be_inspected(self):
        with patch("scripts.task_storage.docker_output", side_effect=subprocess.TimeoutExpired("docker", 30)):
            with self.assertRaises(subprocess.TimeoutExpired):
                require_unused(self.root, "unix:///fixture")

    def test_termination_is_forwarded_and_waits_for_harbor_exit(self):
        code = (
            'import os, signal, time\n'
            'signal.signal(signal.SIGTERM, lambda *_: exit(23))\n'
            'os.kill(os.getppid(), signal.SIGTERM)\n'
            'time.sleep(5)\n'
        )
        previous = signal.getsignal(signal.SIGTERM)
        self.assertEqual(run_command([sys.executable, "-c", code], dict(os.environ), self.root), 23)
        self.assertEqual(signal.getsignal(signal.SIGTERM), previous)


if __name__ == "__main__":
    unittest.main()
