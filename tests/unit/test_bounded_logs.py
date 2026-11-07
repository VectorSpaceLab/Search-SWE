"""Bounded log transport, host metadata protection and safe snapshots."""
import importlib.util
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from harbor.environments.capabilities import EnvironmentCapabilities
from scripts.evaluation.bounded_logs import BoundedLogs, configuration, merge_logs
from scripts.evaluation import bounded_logs

ROOT = Path(__file__).resolve().parents[2]


class LogFiles(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def test_only_regular_files_are_merged_and_host_metadata_is_preserved(self):
        source, target = self.root / "incoming", self.root / "archive"
        source.mkdir(); target.mkdir()
        (source / "harness.json").write_text("untrusted override")
        (target / "harness.json").write_text("verified host metadata")
        (source / "sessions").mkdir()
        (source / "sessions/trace.jsonl").write_text("actual log")
        private = self.root / "private"
        private.write_text("private host content")
        (source / "leak.json").symlink_to(private)
        (source / "external").symlink_to(self.root, target_is_directory=True)
        merge_logs(source, target)
        self.assertEqual((target / "harness.json").read_text(), "verified host metadata")
        self.assertEqual((target / "sessions/trace.jsonl").read_text(), "actual log")
        self.assertFalse((target / "leak.json").exists())
        self.assertFalse((target / "external").exists())
        self.assertEqual(private.read_text(), "private host content")

    def test_task_snapshot_skips_links_and_pipes_without_altering_source_hardlinks(self):
        spec = importlib.util.spec_from_file_location("formula_log_snapshot", ROOT / "tasks/large-scale-formula-retrieval/environment/budget_evidence.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        source, target = self.root / "source", self.root / "target"
        source.mkdir(); target.mkdir()
        original = self.root / "submission.py"
        original.write_text("print('ready')"); original.chmod(0o640)
        (source / "hardlink.log").hardlink_to(original)
        before = original.stat()
        (source / "external").symlink_to(self.root, target_is_directory=True)
        (source / "credential.json").symlink_to(original)
        import os
        os.mkfifo(source / "blocked-pipe")
        module.copy_logs(source, target)
        self.assertEqual(list(p.name for p in target.iterdir()), ["hardlink.log"])
        self.assertEqual((target / "hardlink.log").read_text(), original.read_text())
        after = original.stat()
        self.assertEqual((before.st_uid, before.st_gid, before.st_mode), (after.st_uid, after.st_gid, after.st_mode))

    def test_configuration_requires_an_explicit_trusted_finalizer(self):
        self.assertIsNone(configuration(self.root))
        compose = self.root / "docker-compose.yaml"
        compose.write_text("services:\n  main: {}\n")
        self.assertIsNone(configuration(self.root))
        for value in ("finalize: echo hi", "finalize: []", "finalize: [python, /task/freeze.py]", "arbitrary: true"):
            compose.write_text("x-search-swe:\n  bounded_agent_logs:\n    " + value + "\n")
            with self.assertRaises(ValueError):
                configuration(self.root)

    def test_untrusted_atif_is_discarded_and_framework_published_atif_is_kept(self):
        import os
        spec = importlib.util.spec_from_file_location("formula_log_snapshot", ROOT / "tasks/large-scale-formula-retrieval/environment/budget_evidence.py")
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        source, target = self.root / "source", self.root / "target"
        source.mkdir(); target.mkdir()
        artifact = source / "trajectory.json"; artifact.write_text('{"steps":[]}')
        original = Path.lstat
        owner = 10001
        def ownership(path):
            info = original(path)
            return SimpleNamespace(st_mode=info.st_mode, st_size=info.st_size,
                                   st_blocks=info.st_blocks, st_uid=owner if path == artifact else info.st_uid)
        with patch.object(Path, "lstat", ownership):
            module.copy_logs(source, target)
            self.assertFalse((target / "trajectory.json").exists())
            owner = 0
            module.copy_logs(source, target)
            self.assertEqual((target / "trajectory.json").read_text(), artifact.read_text())

    def test_freeze_waits_for_live_writers_and_rejects_surviving_processes(self):
        spec = importlib.util.spec_from_file_location("formula_log_snapshot", ROOT / "tasks/large-scale-formula-retrieval/environment/budget_evidence.py")
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        status = self.root / "status"
        running = 'Uid:\t10001 10001 10001 10001\nState:\tR (running)\n'
        zombie = running.replace('R (running)', 'Z (zombie)')
        with patch.object(module.subprocess, "run"), patch.object(Path, "glob", return_value=[status]), \
                patch.object(Path, "read_text", side_effect=[running, zombie]), patch.object(module.time, "sleep") as sleep:
            module.stop_solver()
            sleep.assert_called_once()
        with patch.object(module.subprocess, "run"), patch.object(Path, "glob", return_value=[status]), \
                patch.object(Path, "read_text", return_value=running), patch.object(module.time, "monotonic", side_effect=[0, 11]):
            with self.assertRaisesRegex(RuntimeError, "survived"):
                module.stop_solver()

    def snapshot_module(self):
        spec = importlib.util.spec_from_file_location("formula_log_budget", ROOT / "tasks/large-scale-formula-retrieval/environment/budget_evidence.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertEqual(module.MAX_LOG_ARCHIVE_BYTES, bounded_logs.MAX_LOG_ARCHIVE_BYTES)
        return module

    def test_sparse_archive_is_rejected_before_any_copy_and_source_is_retained(self):
        module = self.snapshot_module()
        source, target = self.root / "source", self.root / "target"
        source.mkdir(); target.mkdir()
        sparse = source / "sparse.log"
        with sparse.open("wb") as stream:
            stream.truncate(1 << 30)
        self.assertEqual(sparse.stat().st_blocks, 0)
        with patch.object(module.shutil, "copyfile") as copy:
            with self.assertRaisesRegex(RuntimeError, "512 MiB"):
                module.copy_logs(source, target)
            copy.assert_not_called()
        with self.assertRaisesRegex(RuntimeError, "512 MiB"):
            merge_logs(source, target)
        self.assertEqual(list(target.iterdir()), [])
        self.assertEqual(sparse.stat().st_size, 1 << 30)
        self.assertEqual(sparse.stat().st_blocks, 0)

    def test_hardlink_expansion_is_charged_per_path_before_copying(self):
        module = self.snapshot_module()
        source, target = self.root / "source", self.root / "target"
        source.mkdir(); target.mkdir()
        original = source / "original.log"
        with original.open("wb") as stream:
            stream.truncate(1 << 20)
        for number in range(3):
            (source / str(number)).hardlink_to(original)
        self.assertEqual(len({entry.stat().st_ino for entry in source.iterdir()}), 1)
        self.assertEqual(sum(entry.stat().st_blocks for entry in source.iterdir()), 0)
        with patch.object(module, "MAX_LOG_ARCHIVE_BYTES", 2 << 20), \
                patch.object(bounded_logs, "MAX_LOG_ARCHIVE_BYTES", 2 << 20):
            with self.assertRaisesRegex(RuntimeError, "diagnostic reserve"):
                module.copy_logs(source, target)
            with self.assertRaisesRegex(RuntimeError, "diagnostic reserve"):
                merge_logs(source, target)
        self.assertEqual(list(target.iterdir()), [])

    def test_empty_entry_overhead_is_bounded_and_trajectory_directory_is_checked(self):
        module = self.snapshot_module()
        source = self.root / "source"; source.mkdir()
        (source / "one").mkdir(); (source / "two").mkdir()
        for checker in (module, bounded_logs):
            with patch.object(checker, "MAX_LOG_ARCHIVE_BYTES", 8192):
                with self.assertRaisesRegex(RuntimeError, "diagnostic reserve"):
                    checker.check_log_budget(source)
        folder = source / "trajectory.json"; folder.mkdir()
        with (folder / "large.log").open("wb") as stream:
            stream.truncate(1 << 30)
        with self.assertRaisesRegex(RuntimeError, "diagnostic reserve"):
            module.check_log_budget(source)


class ParentEnvironment:
    def __init__(self, environment_dir, trial_paths):
        self._mounts = [{"target": name} for name in ("/logs/agent", "/logs/verifier", "/logs/artifacts", "/extra")]
        self.trial_paths = trial_paths
        self.exec = AsyncMock(return_value=SimpleNamespace(return_code=0, stdout="", stderr=""))
        self.copies = []

    @property
    def capabilities(self):
        return EnvironmentCapabilities(mounted=True)

    async def download_dir(self, source_dir, target_dir):
        self.copies.append((source_dir, target_dir))
        Path(target_dir).mkdir(exist_ok=True)
        (Path(target_dir) / "pi.txt").write_text("fixture event log")


class TestEnvironment(BoundedLogs, ParentEnvironment):
    pass


class LogTransport(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        (self.root / "docker-compose.yaml").write_text('x-search-swe:\n  bounded_agent_logs:\n    finalize: ["/usr/bin/python3", "/task/logs.py", "freeze"]\n')
        self.environment = TestEnvironment(environment_dir=self.root, trial_paths=SimpleNamespace(trial_dir=self.root))

    async def test_bounded_logs_use_download_conversion_and_upload_lifecycle(self):
        self.assertFalse(self.environment.capabilities.mounted)
        self.assertEqual(self.environment._mounts, [{"target": "/extra"}])
        archive = self.root / "archive"
        await self.environment.download_dir("/logs/agent", archive)
        await self.environment.download_dir("/logs/agent", archive)
        self.assertEqual((archive / "pi.txt").read_text(), "fixture event log")
        self.environment.exec.assert_awaited_once_with("/usr/bin/python3 /task/logs.py freeze", user="root", timeout_sec=120)

    async def test_failed_freeze_is_reported_before_copying_logs(self):
        self.environment.exec.return_value.return_code = 1
        self.environment.exec.return_value.stderr = "synthetic freeze failure"
        with self.assertRaisesRegex(RuntimeError, "freeze failure"):
            await self.environment.download_dir("/logs/agent", self.root / "archive")
        self.assertFalse(self.environment.copies)
        self.assertFalse(self.environment._bounded_logs_finalized)
        self.assertIn("freeze failure", (self.root / "bounded-logs-error.txt").read_text())
        with self.assertRaisesRegex(RuntimeError, "freeze failure"):
            await self.environment.finalize_agent_logs()
        self.environment.exec.assert_awaited_once()

    async def test_other_paths_and_ordinary_environments_keep_their_transport(self):
        await self.environment.download_dir("/app/submission", self.root / "submission")
        self.environment.exec.assert_not_awaited()
        (self.root / "docker-compose.yaml").write_text("services:\n  main: {}\n")
        ordinary = TestEnvironment(environment_dir=self.root, trial_paths=self.environment.trial_paths)
        self.assertTrue(ordinary.capabilities.mounted)
        self.assertEqual(len(ordinary._mounts), 4)

    async def test_finalization_follows_export_and_failure_aborts_the_agent_phase(self):
        events = []
        class BaseAgent:
            async def run(self, *args):
                events.append("run")
        class Export:
            async def run(self, *args):
                await super().run(*args)
                events.append("ATIF export")
        class Agent(bounded_logs.FinalizeBoundedLogs, Export, BaseAgent):
            pass
        async def finalize():
            events.append("freeze")
            raise RuntimeError("log archive exceeds reserve")
        environment = SimpleNamespace(_bounded_agent_logs={"finalize": ["/task/freeze"]}, finalize_agent_logs=finalize)
        with self.assertRaisesRegex(RuntimeError, "archive exceeds"):
            await Agent().run("task", environment, None)
        self.assertEqual(events, ["run", "ATIF export", "freeze"])

    async def test_host_generating_agent_is_checked_without_a_post_run_callback(self):
        class BaseAgent:
            async def run(self, instruction, environment, context):
                with (self.logs_dir / "trajectory.json").open("wb") as stream:
                    stream.truncate(1 << 30)
                context.n_input_tokens = 1  # Harbor skips post-run conversion.
        class Agent(bounded_logs.FinalizeBoundedLogs, BaseAgent):
            pass
        agent = Agent(); agent.logs_dir = self.root
        environment = SimpleNamespace(_bounded_agent_logs={"finalize": ["/task/freeze"]},
                                      finalize_agent_logs=AsyncMock())
        with self.assertRaisesRegex(RuntimeError, "512 MiB"):
            await agent.run("task", environment, SimpleNamespace())
        environment.finalize_agent_logs.assert_awaited_once()

    async def test_host_atif_expansion_fails_before_upload_and_verification(self):
        class BaseAgent:
            def populate_context_post_run(self, context):
                with (self.logs_dir / "trajectory.json").open("wb") as stream:
                    stream.truncate(1 << 30)
        class Agent(bounded_logs.FinalizeBoundedLogs, BaseAgent):
            pass
        agent = Agent()
        agent.logs_dir = self.root
        agent._bounded_logs_enabled = True
        with self.assertRaisesRegex(RuntimeError, "512 MiB"):
            agent.populate_context_post_run(None)


if __name__ == '__main__':
    unittest.main()
