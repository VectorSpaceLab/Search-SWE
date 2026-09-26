import copy
import json
from pathlib import Path
import tempfile
import unittest

from scripts.egress.config import direct_config, load_config
from scripts.egress.compose import NETWORK, SERVICE, declared_services, validate_final


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.path = self.root / "egress.json"
        self.config = {"version": 1, "image": "searchswe-egress:dev1",
                       "upstream": {"url": "https://proxy.example:8080", "address": "192.0.2.1"},
                       "dns": {"doh_url": "https://resolver.example/dns-query"}}

    def load(self):
        self.path.write_text(json.dumps(self.config))
        return load_config(self.path)

    def test_bootstrap_does_not_resolve_dns(self):
        config = self.load()
        self.assertEqual(config.settings["upstream_addr"], "192.0.2.1:8080")
        self.assertEqual(config.settings["upstream_host"], "proxy.example")
        del self.config["upstream"]["address"]
        with self.assertRaisesRegex(ValueError, "explicit IPv4"):
            self.load()

    def test_no_embedded_credentials_or_url_queries(self):
        for url in ("https://user:sensitive-value@proxy.example", "http://proxy.example/?token=sensitive-value",
                    "socks5://proxy.example", "http://proxy.example/path", "http://[::1]", "http://proxy.example:bad"):
            self.config["upstream"]["url"] = url
            with self.subTest(url=url), self.assertRaises(ValueError) as caught:
                self.load()
            self.assertNotIn("sensitive-value", str(caught.exception))

    def test_doh_requires_https(self):
        self.config["dns"]["doh_url"] = "http://resolver.example/dns-query"
        with self.assertRaises(ValueError):
            self.load()

    def test_direct_defaults_and_explicit_dns(self):
        settings = direct_config().private_settings()
        self.assertEqual(settings, {"transport": "direct", "dns_servers": ["127.0.0.11"]})
        self.config = {"version": 1, "mode": "direct", "image": "fixture:direct", "dns": {"servers": ["192.0.2.53"]}}
        self.assertEqual(self.load().settings["dns_servers"], ["192.0.2.53"])
        self.config["upstream"] = {"url": "http://192.0.2.1"}
        with self.assertRaisesRegex(ValueError, "must not specify"):
            self.load()

    def test_direct_dns_rejects_unusable_or_ambiguous_addresses(self):
        for servers in ([], "192.0.2.53", [True], ["127.0.0.1"], ["0.0.0.0"], ["::1"],
                        ["resolver.example"], ["169.254.169.254"], ["224.0.0.1"], ["127.0.0.11:5353"],
                        ["192.0.2.53:٥٣"], ["192.0.2.53:"], ["192.0.2.53:0"], ["192.0.2.53:65536"]):
            with self.subTest(servers=servers), self.assertRaises(ValueError):
                direct_config(dns_servers=servers)

    def test_upstream_cannot_be_task_loopback_or_metadata(self):
        for address in ("127.0.0.1", "0.0.0.0", "169.254.169.254", "224.0.0.1", True):
            self.config["upstream"]["address"] = address
            with self.subTest(address=address), self.assertRaises(ValueError):
                self.load()

    def test_strict_schema(self):
        for value in (True, 2, "1"):
            self.config["version"] = value
            with self.assertRaises(ValueError):
                self.load()
        self.config["version"] = 1
        self.config["upstream"]["password"] = "forbidden-inline-value"
        with self.assertRaises(ValueError):
            self.load()

    def test_secret_permissions_and_symlinks(self):
        secret = self.root / "credentials.json"
        secret.write_text(json.dumps({"username": "fixture", "password": "not-a-real-secret"}))
        secret.chmod(0o600)
        self.config["upstream"]["auth_file"] = "credentials.json"
        config = self.load()
        self.assertNotIn("not-a-real-secret", repr(config))
        self.assertNotIn("auth", config.settings)
        self.assertEqual(config.private_settings()["auth"]["password"], "not-a-real-secret")
        secret.chmod(0o644)
        with self.assertRaisesRegex(ValueError, "0600"):
            config.private_settings()
        secret.chmod(0o600)
        alias = self.root / "alias.json"
        alias.symlink_to(secret)
        self.config["upstream"]["auth_file"] = "alias.json"
        with self.assertRaises(OSError):
            self.load().private_settings()


class ComposeTests(unittest.TestCase):
    def setUp(self):
        self.document = {"name": "unique-trial", "networks": {"default": {"name": "unique-trial_default"}},
                         "services": {SERVICE: {"image": "sha256:fixture", "networks": {"default": {}},
                                                "read_only": True, "tmpfs": ["/run/searchswe:mode=0700"],
                                                "entrypoint": ["/opt/egress-sidecar/entrypoint.sh"]},
                                      "main": {"network_mode": NETWORK, "cap_drop": ["NET_RAW", "NET_ADMIN"],
                                               "security_opt": ["no-new-privileges:true"],
                                               "depends_on": {SERVICE: {"condition": "service_healthy"}}}}}

    def validate(self, document=None):
        validate_final(document or self.document, private_directory="/tmp/private-egress-unique", image="sha256:fixture")

    def test_hardened_compose(self):
        self.validate()

    def test_all_untrusted_services_checked(self):
        self.document["services"]["helper"] = {"image": "python"}
        with self.assertRaises(ValueError):
            self.validate()

    def test_privilege_topology_and_control_mount_rejection(self):
        # Keep each mutation independent of every other guard.
        cases = [{"cap_add": ["SYS_ADMIN"]}, {"cap_drop": []}, {"privileged": True}, {"pid": "host"},
                 {"ipc": "host"}, {"network_mode": "host"}, {"security_opt": ["seccomp:unconfined"]}]
        cases += [{"volumes": [{"type": "bind", "source": source, "target": "/host"}]}
                  for source in ("/tmp/private-egress-unique", "/tmp", "/", "/proc/sys", "/sys", "/var", "/run/docker.sock")]
        for change in cases:
            document = copy.deepcopy(self.document)
            document["services"]["main"].update(change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.validate(document)

    def test_raw_explicit_topology_and_reserved_service_rejected(self):
        for document in ({"services": {SERVICE: {}}}, {"services": {"side": {"network_mode": "host"}}},
                         {"networks": {"custom": {}}}):
            with self.assertRaises(ValueError):
                declared_services([document])
        self.assertEqual(declared_services([{"services": {"helper": {"image": "python"}}}]), ["helper", "main"])

    def test_agent_cannot_modify_config_used_by_next_verifier(self):
        self.document["services"]["main"]["volumes"] = [{"type": "bind", "source": "/home/operator/settings",
                                                         "target": "/workspace"}]
        with self.assertRaisesRegex(ValueError, "gateway configuration"):
            validate_final(self.document, private_directory="/tmp/private-egress-unique", image="sha256:fixture",
                           protected_paths=["/home/operator/settings/egress.json"])

    def test_task_build_cannot_copy_private_config_or_request_host_privileges(self):
        for build in ({"context": "/tmp"}, {"context": "/safe", "network": "host"},
                      {"context": "/safe", "additional_contexts": {"host": "/tmp"}},
                      {"context": "/safe", "secrets": ["proxy-auth"]}):
            self.document["services"]["main"]["build"] = build
            with self.subTest(build=build), self.assertRaises(ValueError):
                self.validate()

    def test_named_volume_cannot_hide_host_bind_or_external_driver(self):
        for change in ({"driver_opts": {"type": "none", "o": "bind", "device": "/"}},
                       {"driver": "external-plugin"}):
            self.document["volumes"] = {"data": {"name": "unique-trial_data", **change}}
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.validate()

    def test_plain_project_local_named_volume_is_supported(self):
        self.document["volumes"] = {"data": {"name": "unique-trial_data", "driver": "local"}}
        self.validate()


if __name__ == "__main__":
    unittest.main()
