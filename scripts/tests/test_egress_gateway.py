import importlib.util
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest import mock


SOURCE = Path(__file__).resolve().parents[2] / "environments/egress/gateway.py"
spec = importlib.util.spec_from_file_location("searchswe_test_gateway", SOURCE)
gateway = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gateway)


class GatewayTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.run = mock.patch.object(gateway, "RUN", self.root)
        self.ready = mock.patch.object(gateway, "READY", self.root / "ready")
        self.run.start()
        self.ready.start()
        self.addCleanup(self.run.stop)
        self.addCleanup(self.ready.stop)
        audit = mock.patch.object(gateway.Controller, "audit")
        audit.start()
        self.addCleanup(audit.stop)
        self.settings = {"upstream_ip": "192.0.2.1", "upstream_port": 8080,
                         "upstream_addr": "192.0.2.1:8080", "upstream_host": "proxy.example",
                         "upstream_tls": True, "doh_url": "https://resolver.example/dns-query",
                         "auth": {"username": "fixture", "password": "not-a-real-secret"}}

    def test_exact_host_policy_only(self):
        for host in ("*.example", "1.2.3.4", "[::1]", "name.example:443", "UPPER.example",
                     "name.example\n", "a..example", "-a.example", "local", 1):
            with self.subTest(host=host), self.assertRaises(ValueError):
                gateway.policy("allowlist", [host])
        self.assertEqual(gateway.policy("allowlist", ["a.example", "a.example"])["hosts"], ["a.example"])
        for mode in ("public", "allow-all", "none"):
            with self.assertRaises(ValueError):
                gateway.policy(mode, [])

    def test_config_marks_tls_and_no_fallback(self):
        config = gateway.gost_config(self.settings, ["allowed.example"])
        node = config["chains"][0]["hops"][0]["nodes"][0]
        self.assertEqual(node["dialer"]["tls"], {"serverName": "proxy.example", "secure": True})
        self.assertEqual(node["metadata"]["so_mark"], "114514")
        for service in config["services"]:
            self.assertEqual(service["metadata"]["so_mark"], "114514")
            self.assertEqual(service["handler"]["chain"], "operator")
        self.assertFalse(config["services"][0]["handler"]["metadata"]["sniffing.fallback"])
        self.assertNotIn("api", config)

    def test_direct_routing_uses_filtered_resolver_without_proxy(self):
        config = gateway.gost_config({"transport": "direct", "dns_servers": ["192.0.2.53"]}, ["allowed.example"])
        self.assertNotIn("chains", config)
        self.assertEqual(config["services"][0]["resolver"], "phase-dns")
        self.assertEqual(config["resolvers"][0]["nameservers"][0]["only"], "ipv4")
        for service in config["services"]:
            self.assertNotIn("chain", service["handler"])
            self.assertEqual(service["bypass"], "phase")

    def test_direct_public_is_leased_and_restriction_removes_public_mark(self):
        controller = gateway.Controller({"transport": "direct", "dns_servers": ["127.0.0.11"]})
        commands = []
        with mock.patch.object(gateway, "nft", side_effect=commands.append):
            controller.apply({"mode": "public", "hosts": [], "deadline_ns": time.monotonic_ns() + 30 * 10**9})
            self.assertTrue(any(", 0 timeout" in command for command in commands))
            self.assertEqual(commands[-1], "delete table inet searchswe_guard\n")
            commands.clear()
            controller.apply({"mode": "no-network", "hosts": [], "deadline_ns": time.monotonic_ns() + 30 * 10**9})
            self.assertFalse(any(", 0 timeout" in command for command in commands))
            self.assertFalse(any(command.startswith("delete table") for command in commands))

    def test_generation_closes_gate_before_killing_and_opens_last(self):
        commands = []
        worker = mock.Mock()
        worker.poll.return_value = None
        worker.terminate.side_effect = lambda: commands.append("terminate")
        controller = gateway.Controller(self.settings)
        with mock.patch.object(gateway, "nft", side_effect=commands.append), \
             mock.patch.object(gateway.subprocess, "Popen", return_value=worker), \
             mock.patch.object(gateway, "owns_listeners", return_value=True):
            state = controller.apply({"mode": "allowlist", "hosts": ["allowed.example"],
                                      "deadline_ns": time.monotonic_ns() + 30 * 10**9})
            self.assertTrue(state["ready"])
            self.assertNotIn("not-a-real-secret", json.dumps(state))
            self.assertEqual(commands[-1], "delete table inet searchswe_guard\n")
            commands.clear()
            state = controller.apply({"mode": "no-network", "hosts": [],
                                      "deadline_ns": time.monotonic_ns() + 30 * 10**9})
            self.assertIn("priority -300", commands[0])
            self.assertEqual(commands[1], "terminate")
            self.assertFalse(any(c.startswith("delete table") for c in commands))
            self.assertIsNone(controller.worker)
            self.assertEqual(state["generation"], 2)

    def test_invalid_replacement_and_failed_worker_remain_closed(self):
        controller = gateway.Controller(self.settings)
        worker = mock.Mock()
        worker.poll.return_value = 1
        with mock.patch.object(gateway, "nft") as nft, \
             mock.patch.object(gateway.subprocess, "Popen", return_value=worker):
            for request in ({"mode": "allowlist", "hosts": ["*.example"]},
                            {"mode": "allowlist", "hosts": ["allowed.example"]}):
                with self.assertRaises((ValueError, RuntimeError)):
                    controller.apply({**request, "deadline_ns": time.monotonic_ns() + 30 * 10**9})
                self.assertFalse(controller.state["ready"])
                self.assertFalse(gateway.READY.exists())
                self.assertFalse(any(c.args[0].startswith("delete table") for c in nft.call_args_list))

    def test_nft_interpolation_revalidates_settings(self):
        with mock.patch.object(gateway, "nft") as nft:
            for ip in ("::1", "192.0.2.1; flush ruleset", "proxy.example"):
                with self.assertRaises(ValueError):
                    gateway.install_rules({**self.settings, "upstream_ip": ip})
            nft.assert_not_called()

    def test_upstream_cannot_target_shared_namespace(self):
        with mock.patch.object(gateway.subprocess, "run") as run:
            run.return_value.stdout = "local 192.0.2.1 dev lo src 192.0.2.1"
            with self.assertRaises(ValueError):
                gateway.validate_upstream_namespace(self.settings)
            run.return_value.stdout = "192.0.2.1 via 172.18.0.1 dev eth0"
            gateway.validate_upstream_namespace(self.settings)

    def test_expired_lease_cannot_be_renewed_into_old_permissions(self):
        controller = gateway.Controller(self.settings)
        controller.state = {"ready": True}
        controller.deadline_ns = time.monotonic_ns() - 1
        with mock.patch.object(gateway, "nft") as nft:
            with self.assertRaises(RuntimeError):
                controller.renew(time.monotonic_ns() + 30 * 10**9)
            self.assertFalse(controller.state["ready"])
            self.assertFalse(any("add element" in c.args[0] for c in nft.call_args_list))

    def test_direct_dns_cannot_be_impersonated_inside_task_namespace(self):
        with mock.patch.object(gateway.subprocess, "run") as run:
            run.return_value.stdout = "local 192.0.2.53 dev lo src 192.0.2.53"
            with self.assertRaisesRegex(ValueError, "outside the shared task"):
                gateway.validate_upstream_namespace({"transport": "direct", "dns_servers": ["192.0.2.53"]})
            run.reset_mock()
            gateway.validate_upstream_namespace({"transport": "direct", "dns_servers": ["127.0.0.11:53"]})
            run.assert_not_called()
            with self.assertRaisesRegex(ValueError, "port 53"):
                gateway.validate_upstream_namespace({"transport": "direct", "dns_servers": ["127.0.0.11:5353"]})
            run.return_value.stdout = "192.0.2.53 via 172.18.0.1 dev eth0"
            gateway.validate_upstream_namespace({"transport": "direct", "dns_servers": ["192.0.2.53:5353"]})

    def test_lease_uses_bounded_kernel_timeout_and_absolute_cutoff(self):
        controller = gateway.Controller(self.settings)
        with mock.patch.object(gateway, "nft") as nft:
            controller.refresh_lease(time.monotonic_ns() + 30 * 10**9)
            command = nft.call_args.args[0]
            self.assertIn("timeout ", command)
            self.assertIn('meta time < "', command)
            for deadline in (0, True, time.monotonic_ns() + 60 * 10**9):
                with self.assertRaises(ValueError):
                    controller.refresh_lease(deadline)

    def test_nft_failure_still_terminates_worker(self):
        controller = gateway.Controller(self.settings)
        worker = mock.Mock()
        worker.poll.return_value = None
        controller.worker = worker
        with mock.patch.object(gateway, "nft", side_effect=RuntimeError("fixture failure")):
            with self.assertRaises(RuntimeError):
                controller.fail()
        worker.terminate.assert_called_once()
        self.assertFalse(controller.state["ready"])


if __name__ == "__main__":
    unittest.main()
