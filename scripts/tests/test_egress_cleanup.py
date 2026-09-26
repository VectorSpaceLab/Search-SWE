import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import egress_cleanup
from scripts.egress import ownership


class OrphanCleanupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = patch.object(ownership, "owner_root", return_value=Path(self.temp.name))
        root.start()
        self.addCleanup(root.stop)
        self.private = ownership.PrivateDirectory("fixture", "project", "image", daemon_id="fixture-daemon")

    def test_dry_run_does_not_remove_resources_or_private_files(self):
        with patch.object(egress_cleanup, "inventory", return_value=[]), patch.object(egress_cleanup, "docker") as docker:
            result = egress_cleanup.recover(self.private.name)
        self.assertFalse(result["removed"])
        docker.assert_not_called()
        self.assertTrue(Path(self.private.name).exists())

    def test_live_project_owner_prevents_recovery(self):
        lock = ownership.ProjectLock("project")
        try:
            with self.assertRaises(BlockingIOError):
                egress_cleanup.recover(self.private.name, remove=True)
        finally:
            lock.close()

    def test_context_overrides_host_and_remote_cleanup_is_refused(self):
        context = [{"Endpoints": {"docker": {"Host": "ssh://remote"}}}]
        with patch.dict("os.environ", {"DOCKER_CONTEXT": "remote", "DOCKER_HOST": "unix:///local.sock"}), \
             patch.object(egress_cleanup, "docker", return_value=json.dumps(context)) as docker:
            with self.assertRaisesRegex(ValueError, "local Unix-socket"):
                egress_cleanup.inventory(self.private.manifest)
        self.assertEqual(docker.call_count, 1)

    def test_gateway_removed_first_and_cleanup_is_verified(self):
        resources = [{"kind": kind, "id": name, "gateway": gateway} for kind, name, gateway in
                     [("container", "task", False), ("network", "net", False),
                      ("container", "gateway", True), ("volume", "vol", False)]]
        def remove(*arguments):
            if arguments[:2] == ("container", "inspect"):
                return json.dumps([{"State": {"Running": True}}])
            if arguments[0] == "logs":
                return '{"event":"lease_expired","instance":"fixture"}\n'
            if arguments[:2] == ("container", "kill"):
                return "gateway"
            resources[:] = [r for r in resources if r["id"] != arguments[-1]]
        with patch.object(egress_cleanup, "inventory", side_effect=lambda _: resources[:]), \
             patch.object(egress_cleanup, "docker", side_effect=remove) as docker:
            result = egress_cleanup.recover(self.private.name, remove=True)
        self.assertTrue(result["removed"])
        calls = [call.args for call in docker.call_args_list]
        self.assertEqual(calls[:4], [("container", "inspect", "gateway"), ("container", "kill", "gateway"),
                                     ("logs", "gateway"), ("container", "rm", "-f", "gateway")])
        audit = Path(result["audit_paths"][0])
        self.assertIn("lease_expired", audit.read_text())
        self.assertEqual(audit.stat().st_mode & 0o777, 0o600)
        self.assertFalse(Path(self.private.name).exists())

    def test_audit_failure_preserves_stopped_gateway_and_manifest(self):
        resource = {"kind": "container", "id": "gateway", "gateway": True}
        replies = [json.dumps([{"State": {"Running": True}}]), "gateway", '{"event":"closed"}\n']
        with patch.object(egress_cleanup, "inventory", return_value=[resource]), \
             patch.object(egress_cleanup, "docker", side_effect=replies) as command, \
             patch.object(egress_cleanup.tempfile, "mkstemp", side_effect=OSError("fixture disk error")):
            with self.assertRaises(OSError):
                egress_cleanup.recover(self.private.name, remove=True)
        self.assertEqual(command.call_args_list[1].args, ("container", "kill", "gateway"))
        self.assertFalse(any("rm" in call.args for call in command.call_args_list))
        self.assertTrue((Path(self.private.name) / "owner.json").exists())

    def test_docker_failure_preserves_recovery_manifest(self):
        resources = [{"kind": "container", "id": "gateway", "gateway": True}]
        with patch.object(egress_cleanup, "inventory", return_value=resources), \
             patch.object(egress_cleanup, "docker", side_effect=RuntimeError("fixture offline")):
            with self.assertRaises(RuntimeError):
                egress_cleanup.recover(self.private.name, remove=True)
        self.assertTrue((Path(self.private.name) / "owner.json").is_file())

    def test_foreign_project_label_is_rejected_before_mutation(self):
        def inspect(*arguments):
            if arguments[:2] == ("context", "inspect"):
                return json.dumps([{"Endpoints": {"docker": {"Host": "unix:///fixture.sock"}}}])
            if arguments[:2] == ("info", "--format"):
                return json.dumps("fixture-daemon")
            if arguments[:2] == ("container", "ls"):
                return "fixture-id\n"
            if arguments[:2] == ("container", "inspect"):
                return json.dumps([{"Config": {"Labels": {ownership.LABEL: "fixture", "com.docker.compose.project": "FOREIGN"}}}])
            raise AssertionError(arguments)
        with patch.object(egress_cleanup, "docker", side_effect=inspect), patch.dict("os.environ", {"DOCKER_HOST": "unix:///fixture.sock"}):
            with self.assertRaisesRegex(ValueError, "ownership mismatch"):
                egress_cleanup.inventory(self.private.manifest)

    def test_wrong_local_daemon_does_not_discard_recovery_manifest(self):
        responses = [json.dumps([{"Endpoints": {"docker": {"Host": "unix:///different.sock"}}}]),
                     json.dumps("different-daemon")]
        with patch.object(egress_cleanup, "docker", side_effect=responses) as docker:
            with self.assertRaisesRegex(ValueError, "daemon identity mismatch"):
                egress_cleanup.recover(self.private.name, remove=True)
        self.assertEqual(docker.call_count, 2)
        self.assertTrue((Path(self.private.name) / "owner.json").exists())


class OwnershipTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        root = patch.object(ownership, "owner_root", return_value=self.root)
        root.start()
        self.addCleanup(root.stop)

    def test_project_lock_excludes_concurrent_owners_and_releases(self):
        first = ownership.ProjectLock("fixture-project")
        self.addCleanup(first.close)
        with self.assertRaises(BlockingIOError):
            ownership.ProjectLock("fixture-project")
        first.close()
        second = ownership.ProjectLock("fixture-project")
        second.close()

    def test_private_manifest_is_recoverable_without_gc_cleanup(self):
        directory = ownership.PrivateDirectory("fixture", "project", "sha256:fixture")
        name = directory.name
        del directory
        self.assertTrue(Path(name).is_dir())
        self.assertEqual(ownership.read_manifest(name)["instance"], "fixture")

    def test_manifest_change_or_symlink_prevents_removal(self):
        directory = ownership.PrivateDirectory("fixture", "project", "sha256:fixture")
        manifest = Path(directory.name) / "owner.json"
        manifest.unlink()
        target = self.root / "unrelated"
        target.write_text("must survive")
        manifest.symlink_to(target)
        with self.assertRaises(OSError):
            directory.cleanup()
        self.assertEqual(target.read_text(), "must survive")
