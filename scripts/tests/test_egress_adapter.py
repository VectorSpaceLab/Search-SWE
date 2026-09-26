"""Host lifecycle failure tests; these do not substitute for Docker gates."""

from pathlib import Path
import json
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from scripts.harbor_environments import PhaseScopedDocker, DockerEnvironment, gateway_image_info
from scripts.egress import ownership


class AdapterCleanupTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.root = tempfile.TemporaryDirectory()
        self.addCleanup(self.root.cleanup)
        self.env = object.__new__(PhaseScopedDocker)
        self.env._private = tempfile.TemporaryDirectory()
        self.private = Path(self.env._private.name)
        self.env._instance = "fixture"
        self.env._owner_lock = None
        self.env._daemon_id = "fixture-daemon"
        self.env._compose_started = True
        self.env._rendered_document = {"name": "fixture"}
        self.env._check_resource_ownership = Mock()
        self.env.trial_paths = SimpleNamespace(trial_dir=Path(self.root.name) / "missing" / "trial")
        self.env._force_closed = AsyncMock()
        self.env._stop_heartbeat = AsyncMock()
        self.env._require_daemon = AsyncMock()
        self.env.prepare_logs_for_host = AsyncMock()
        self.env._run_docker_compose_command = AsyncMock(return_value=SimpleNamespace(stdout="safe-event\n"))
        for name in ("mounts", "resources", "env", "egress_control_services"):
            setattr(self.env, f"_cleanup_{name}_compose_file", Mock())

    async def test_missing_audit_parent_is_created_and_resources_are_removed(self):
        await self.env.stop(delete=True)
        self.assertFalse(self.private.exists())
        self.assertEqual((self.env.trial_paths.trial_dir / "egress/fixture.log").read_text(), "safe-event\n")
        self.env._run_docker_compose_command.assert_any_await(["down", "--remove-orphans", "--volumes"], timeout_sec=60)

    async def test_audit_write_failure_does_not_skip_down(self):
        with patch.object(Path, "mkdir", side_effect=OSError("fixture full disk")):
            with self.assertRaisesRegex(RuntimeError, "audit collection failed"):
                await self.env.stop(delete=True)
        self.assertFalse(self.private.exists())
        self.env._run_docker_compose_command.assert_any_await(["down", "--remove-orphans", "--volumes"], timeout_sec=60)

    async def test_failed_prelaunch_never_runs_down_against_foreign_resources(self):
        self.env._compose_started = False
        await self.env.stop(delete=True)
        self.env._run_docker_compose_command.assert_not_awaited()
        self.env._force_closed.assert_not_awaited()
        self.assertFalse(self.private.exists())

    async def test_foreign_resource_blocks_down_and_preserves_manifest(self):
        self.env._check_resource_ownership.side_effect = ValueError("not owned")
        with self.assertRaisesRegex(ValueError, "not owned"):
            await self.env.stop(delete=True)
        self.env._run_docker_compose_command.assert_not_awaited()
        self.assertTrue(self.private.exists())
        self.env._stop_heartbeat.assert_awaited_once()
        self.env._private.cleanup()

    async def test_named_volume_ownership_collision(self):
        doc = {"name": "fixture", "volumes": {"data": {"name": "fixture_data"}}}
        response = SimpleNamespace(returncode=0, stdout='[{"Labels":{}}]', stderr="")
        with patch("scripts.harbor_environments.subprocess.run", return_value=response), \
             patch("scripts.harbor_environments.docker_json", return_value="fixture-daemon"):
            with self.assertRaisesRegex(ValueError, "not owned"):
                PhaseScopedDocker._check_resource_ownership(self.env, doc)
        self.env._private.cleanup()

    async def test_context_overrides_host_when_rejecting_remote_daemon(self):
        with patch.dict("os.environ", {"DOCKER_CONTEXT": "remote", "DOCKER_HOST": "unix:///local.sock"}), \
             patch("scripts.harbor_environments.docker_json", return_value=[{"Endpoints": {"docker": {"Host": "ssh://remote"}}}]):
            with self.assertRaisesRegex(ValueError, "local Unix-socket"):
                self.env._preflight_gateway()
        self.env._private.cleanup()

    async def test_missing_volume_and_network_are_not_foreign_resources(self):
        doc = {"name": "fixture", "volumes": {"data": {"name": "fixture_data"}},
               "networks": {"default": {"name": "fixture_default"}}}
        responses = [SimpleNamespace(returncode=1, stdout="[]", stderr=error) for error in (
            "Error response from daemon: get fixture_data: no such volume",
            "Error response from daemon: network fixture_default not found")]
        responses.append(SimpleNamespace(returncode=0, stdout="", stderr=""))
        with patch("scripts.harbor_environments.subprocess.run", side_effect=responses), \
             patch("scripts.harbor_environments.docker_json", return_value="fixture-daemon"):
            PhaseScopedDocker._check_resource_ownership(self.env, doc)
        self.env._private.cleanup()

    async def test_daemon_change_refuses_resource_mutations(self):
        with patch("scripts.harbor_environments.docker_json", return_value="different-daemon"), \
             patch("scripts.harbor_environments.subprocess.run") as command:
            with self.assertRaisesRegex(ValueError, "identity changed"):
                PhaseScopedDocker._check_resource_ownership(self.env, {"name": "fixture"})
        command.assert_not_called()
        self.env._private.cleanup()

    async def test_different_daemon_kernel_is_rejected_before_resources(self):
        responses = [[{"Endpoints": {"docker": {"Host": "unix:///fixture.sock"}}}],
                     {"OSType": "linux", "Architecture": "amd64", "KernelVersion": "different-kernel"}]
        with patch("scripts.harbor_environments.docker_json", side_effect=responses), \
             patch("scripts.harbor_environments.ProjectLock") as lock:
            with self.assertRaisesRegex(ValueError, "same native"):
                self.env._preflight_gateway()
        lock.assert_not_called()
        self.env._private.cleanup()

    async def test_wrong_daemon_is_not_sent_a_policy_or_kill(self):
        self.env._require_daemon.side_effect = RuntimeError("different daemon")
        with patch("scripts.harbor_environments.asyncio.sleep", new_callable=AsyncMock) as wait:
            with self.assertRaisesRegex(RuntimeError, "cleanup unverified"):
                await PhaseScopedDocker._force_closed(self.env)
        self.env._run_docker_compose_command.assert_not_awaited()
        wait.assert_awaited_once_with(31)
        self.env._private.cleanup()

    async def test_successful_deny_all_also_fences_delayed_remote_execs(self):
        await PhaseScopedDocker._force_closed(self.env)
        self.env._run_docker_compose_command.assert_any_await(
            ["kill", "harbor-docker-egress-control-sidecar"], timeout_sec=30)
        self.assertIsInstance(self.env._heartbeat_error, RuntimeError)
        self.env._private.cleanup()

    async def test_retained_volumes_keep_manifest_but_not_proxy_secret(self):
        self.env._private.cleanup()
        with patch.object(ownership, "owner_root", return_value=Path(self.root.name)):
            managed = ownership.PrivateDirectory("fixture", "fixture", "image")
            self.env._private = managed
            directory = Path(managed.name)
            (directory / "input.json").write_text("fixture-only-private-settings")
            self.env._rendered_document["volumes"] = {"data": {"name": "fixture_data"}}
            await self.env.stop(delete=False)
            self.assertTrue((directory / "owner.json").is_file())
            self.assertFalse((directory / "input.json").exists())
            managed.cleanup()

    async def test_gateway_bootstrap_then_baseline_then_task_start(self):
        self.env._heartbeat = Mock()
        self.env._gateway_image = "fixture"
        self.env._engine_paths = ()
        self.env.egress = SimpleNamespace(path=Path("/private/fixture.json"), auth_path=None)
        self.env._network_policy = Mock()
        calls = []
        async def compose(command, *args, **kwargs):
            calls.append(command)
            return SimpleNamespace(stdout=json.dumps({"name": "fixture", "volumes": {}}))
        async def baseline(policy):
            self.assertIs(policy, self.env.network_policy)
            calls.append("baseline")
        self.env.set_network_policy = AsyncMock(side_effect=baseline)
        with patch.object(DockerEnvironment, "_run_docker_compose_command", side_effect=compose), \
             patch("scripts.harbor_environments.validate_final"):
            await PhaseScopedDocker._run_docker_compose_command(self.env, ["up", "--detach", "--wait"])
        self.assertEqual(calls[1:], [
            ["up", "--detach", "--wait", "--no-deps", "harbor-docker-egress-control-sidecar"],
            "baseline", ["up", "--detach", "--wait"]])
        self.env._private.cleanup()


class GatewayImagePullTests(unittest.TestCase):
    def test_cached_image_needs_no_registry(self):
        with patch("scripts.harbor_environments.docker_json", return_value=[{"Id": "cached"}]), \
             patch("scripts.harbor_environments.subprocess.run") as run:
            self.assertEqual(gateway_image_info("fixture:1"), {"Id": "cached"})
        run.assert_not_called()

    def test_missing_image_is_pulled_then_inspected(self):
        missing = subprocess.CalledProcessError(1, "inspect", stderr="Error: No such image: fixture:1")
        with patch("scripts.harbor_environments.docker_json", side_effect=[missing, [{"Id": "pulled"}]]) as inspect, \
             patch("scripts.harbor_environments.subprocess.run") as run:
            self.assertEqual(gateway_image_info("fixture:1"), {"Id": "pulled"})
        self.assertEqual(inspect.call_count, 2)
        run.assert_called_once_with(["docker", "pull", "--platform", "linux/amd64", "fixture:1"],
                                    check=True, capture_output=True, text=True, timeout=300)

    def test_daemon_error_does_not_attempt_pull(self):
        error = subprocess.CalledProcessError(1, "inspect", stderr="permission denied")
        with patch("scripts.harbor_environments.docker_json", side_effect=error), \
             patch("scripts.harbor_environments.subprocess.run") as run:
            with self.assertRaises(subprocess.CalledProcessError):
                gateway_image_info("fixture:1")
        run.assert_not_called()

    def test_failed_or_timed_out_pull_stops_startup(self):
        missing = subprocess.CalledProcessError(1, "inspect", stderr="No such image: fixture:1")
        for error in (subprocess.CalledProcessError(1, "pull"), subprocess.TimeoutExpired("pull", 300)):
            with self.subTest(error=type(error).__name__), \
                 patch("scripts.harbor_environments.docker_json", side_effect=missing) as inspect, \
                 patch("scripts.harbor_environments.subprocess.run", side_effect=error):
                with self.assertRaisesRegex(RuntimeError, "Could not pull egress gateway"):
                    gateway_image_info("fixture:1")
                inspect.assert_called_once()
