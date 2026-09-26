import json
import os
from pathlib import Path
import subprocess
import shutil
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]


class EgressLauncherTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.env_file = self.root / "empty.env"
        self.env_file.touch()
        self.config = self.root / "egress.json"
        self.document = {"version": 1, "image": "searchswe-egress:dev3",
                         "upstream": {"url": "http://192.0.2.1:8080"},
                         "dns": {"doh_url": "https://resolver.example/dns-query"}}
        self.config.write_text(json.dumps(self.document))

    def launch(self, *arguments, task="task-1-1", env=None, public=False):
        repo = ROOT
        if public:
            # Public-policy coverage must not depend on a benchmark task's
            # evolving network requirements (for example, task-2-3).
            repo = self.root / "repo"
            shutil.copytree(ROOT / "scripts", repo / "scripts",
                            ignore=shutil.ignore_patterns("__pycache__", "tests"))
            task = "task-fixture"
            fixture = repo / "tasks" / task
            fixture.mkdir(parents=True)
            (fixture / "task.toml").write_text(
                '[environment]\nnetwork_mode = "no-network"\n'
                '[agent]\nnetwork_mode = "public"\n'
                '[verifier]\nnetwork_mode = "no-network"\n')
        return subprocess.run(
            [sys.executable, str(repo / "scripts/run_task.py"), "--task", task, "--agent", "pi",
             "--model", "deepseek/deepseek-flash", "--env-file", str(self.env_file), "--dry-run", *arguments],
            env={"PATH": os.environ["PATH"], "HOME": str(self.root), **(env or {})},
            capture_output=True, text=True, timeout=30)

    def test_default_restricted_task_uses_direct_gateway(self):
        response = self.launch()
        self.assertEqual(response.returncode, 0, response.stderr)
        self.assertIn("--env scripts.harbor_environments:PhaseScopedDocker", response.stdout)
        self.assertIn("egress_image=hanhainebula/search-swe-egress:1.0.0", response.stdout)
        self.assertIn("Phase-scoped direct gateway", response.stdout)

    def test_direct_dns_and_image_override(self):
        response = self.launch("--container-dns", "192.0.2.53", "--egress-image", "fixture:direct")
        self.assertEqual(response.returncode, 0, response.stderr)
        self.assertIn("egress_dns=192.0.2.53", response.stdout)
        self.assertIn("egress_image=fixture:direct", response.stdout)
        self.assertNotIn("--extra-docker-compose", response.stdout)

    def test_public_agent_with_restricted_verifier_uses_direct_gateway(self):
        response = self.launch(public=True)
        self.assertEqual(response.returncode, 0, response.stderr)
        self.assertIn("PhaseScopedDocker", response.stdout)

    def test_direct_configuration_supports_public_phases(self):
        self.config.write_text(json.dumps({"version": 1, "mode": "direct", "image": "fixture:direct", "dns": {}}))
        response = self.launch("--egress-config", str(self.config), public=True)
        self.assertEqual(response.returncode, 0, response.stderr)
        self.assertIn("PhaseScopedDocker", response.stdout)

    def test_opt_in_uses_custom_adapter_and_public_path_only(self):
        # Dry-run must not read this absent credential file or inspect Docker.
        self.document["upstream"]["auth_file"] = "not-present.json"
        self.config.write_text(json.dumps(self.document))
        response = self.launch("--egress-config", str(self.config))
        self.assertEqual(response.returncode, 0, response.stderr)
        self.assertIn("--env scripts.harbor_environments:PhaseScopedDocker", response.stdout)
        self.assertIn("--environment-kwarg egress_config=", response.stdout)
        self.assertNotIn("not-present.json", response.stdout)
        self.assertNotIn("CONTAINER_PROXY", response.stdout)

    def test_env_selection_and_cli_override(self):
        response = self.launch(env={"EGRESS_CONFIG": str(self.config)})
        self.assertEqual(response.returncode, 0, response.stderr)
        response = self.launch("--egress-config", str(self.config), env={"EGRESS_CONFIG": "/not/present"})
        self.assertEqual(response.returncode, 0, response.stderr)

    def test_dns_override_conflict_is_explicit(self):
        response = self.launch("--egress-config", str(self.config), env={"CONTAINER_DNS": "192.0.2.53"})
        self.assertNotEqual(response.returncode, 0)
        self.assertIn("clear them explicitly", response.stderr)

    def test_generic_proxy_cannot_bypass_restricted_path(self):
        response = self.launch(env={"CONTAINER_PROXY": "http://192.0.2.1:8080"})
        self.assertNotEqual(response.returncode, 0)
        self.assertIn("general proxy can bypass", response.stderr)

    def test_public_phase_rejected_without_changing_task(self):
        response = self.launch("--egress-config", str(self.config), public=True)
        self.assertNotEqual(response.returncode, 0, response.stdout + response.stderr)
        self.assertIn("any public phase", response.stderr)
        self.assertIn('network_mode = "public"',
                      (self.root / "repo/tasks/task-fixture/task.toml").read_text())

    def test_rejected_url_does_not_echo_embedded_secret(self):
        self.document["upstream"]["url"] = "https://user:do-not-leak-this@proxy.example"
        self.config.write_text(json.dumps(self.document))
        response = self.launch("--egress-config", str(self.config))
        self.assertNotEqual(response.returncode, 0)
        self.assertNotIn("do-not-leak-this", response.stdout + response.stderr)

    def test_proxy_cannot_be_exposed_as_an_allowed_model_host(self):
        self.document["upstream"] = {"url": "https://api.deepseek.com:8443", "address": "192.0.2.1"}
        self.config.write_text(json.dumps(self.document))
        response = self.launch("--egress-config", str(self.config))
        self.assertNotEqual(response.returncode, 0)
        self.assertIn("cannot also be an allowed", response.stderr)


if __name__ == "__main__":
    unittest.main()
