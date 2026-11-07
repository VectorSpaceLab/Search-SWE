"""Harness version selection, verified installs and cache boundaries (no APIs)."""

import asyncio
import json
import os
from pathlib import Path
import stat
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from search_swe import harnesses
from search_swe.configuration import Setting, resolve_setting, saved_setting
from search_swe.cli import parser
from scripts.evaluation import harness_install as manager


class HarnessSelection(unittest.TestCase):
    def test_defaults_and_overrides(self):
        self.assertEqual({name: harnesses.default_version(name) for name in ("codex", "claude-code", "pi")},
                         {"codex": "0.164.0", "claude-code": "2.1.309", "pi": "1.4.0"})
        self.assertEqual(harnesses.resolve_version("codex", "0.165.0", "0.163.0"), "0.165.0")
        self.assertEqual(harnesses.resolve_version("codex", configured="0.163.0"), "0.163.0")
        self.assertEqual(harnesses.resolve_version("codex", "default", "0.163.0"), "0.164.0")
        self.assertIsNone(harnesses.resolve_version("nop"))
        with self.assertRaisesRegex(ValueError, "Harbor helper"):
            harnesses.resolve_version("nop", "1.2.3")
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'src/search_swe/data/harnesses.toml'
            source.parent.mkdir(parents=True)
            source.write_text('schema_version=1\n[agents.codex]\nversion="9.8.7"\n[verifier]\ncodex_version="0.164.0"\n')
            self.assertEqual(harnesses.resolve_version("codex", root=directory), "9.8.7")
            self.assertEqual(harnesses.registry(directory)["verifier"]["codex_version"], "0.164.0")

    def test_versions_are_exact_and_archive_overrides_need_a_registered_release(self):
        for version in ("latest", "1.2", "1.2.", "^1.2.3", "1.2;echo bad", "../1.2", "1.2/3", 123):
            with self.subTest(version=version), self.assertRaises(ValueError):
                harnesses.version_argument(version)
        self.assertEqual(harnesses.install_spec("codex", "v0.163.0")["version"], "0.163.0")
        self.assertEqual(harnesses.install_spec("antigravity-cli")["version"], "1.5.2")
        with self.assertRaisesRegex(ValueError, "SHA-512"):
            harnesses.install_spec("antigravity-cli", "1.5.3")

    def test_saved_pin_stays_on_same_harness_and_can_be_reset(self):
        current = Setting(agent_version="0.163.0")
        self.assertEqual(saved_setting(current.values()), current)
        self.assertEqual(resolve_setting(current, parser().parse_args(["configure"])), current)
        reset = resolve_setting(current, parser().parse_args(["configure", "--agent-version", "default"]))
        self.assertEqual(reset.agent_version, "default")
        self.assertIn("--agent-version", reset.flags())
        changed = resolve_setting(current, parser().parse_args(["configure", "--agent", "pi"]))
        self.assertIsNone(changed.agent_version)
        # Omitting an override remains a live registry default when saved.
        self.assertEqual(Setting().values()["SEARCH_SWE_AGENT_VERSION"], "")

    def test_actual_version_output_is_strict(self):
        for output in ("codex-cli 0.164.0", "WARNING: harmless\ncodex-cli 0.164.0\n",
                       "0.164.0 (Claude Code)", "v0.164.0"):
            self.assertEqual(manager.parse_version(output), "0.164.0")
        for output in ("", "WARNING: expected codex-cli 0.164.0", "1.2.3\n1.2.3", "1.2.3\n2.3.4"):
            with self.assertRaises(RuntimeError):
                manager.parse_version(output)

    def test_installer_has_no_inherited_credentials_and_pins_sources(self):
        command = manager.installation_command(harnesses.install_spec("codex"), "/opt/fixture")
        self.assertIn("env -i", command)
        self.assertIn("NPM_CONFIG_USERCONFIG=/dev/null", command)
        self.assertIn("@openai/codex@0.164.0", command)
        self.assertIn("@openai/codex@0.164.0-linux-x64", command)
        self.assertNotIn("API_KEY", command)
        archive = manager.installation_command(harnesses.install_spec("antigravity-cli"), "/opt/fixture")
        self.assertIn("sha512sum --check", archive)
        self.assertNotIn("install.sh", archive)


class HarnessCache(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.environment = SimpleNamespace(upload_file=AsyncMock(), download_file=AsyncMock(side_effect=self.download))
        self.calls = []
        self.users = []
        self.output = "codex-cli 0.164.0\n"
        self.cache = patch.dict(os.environ, {"SEARCH_SWE_HARNESS_CACHE": str(self.root / "cache")})
        self.cache.start()
        self.addCleanup(self.cache.stop)
        self.image = patch.object(manager, "image_identity", AsyncMock(return_value="sha256:" + "a" * 64))
        self.image_mock = self.image.start()
        self.addCleanup(self.image.stop)
        self.exec_patch = patch.object(manager, "execute", side_effect=self.execute)
        self.exec_patch.start()
        self.addCleanup(self.exec_patch.stop)

    async def execute(self, environment, command, **kwargs):
        self.calls.append(command)
        self.users.append(kwargs.get("user"))
        if command.endswith(" --version"):
            return self.output
        if command == 'printf %s "$PATH"':
            return "/usr/local/bin:/usr/bin:/bin"
        return ""

    async def download(self, *, source_path, target_path):
        # Cache behavior is independent of tar mechanics, tested in real Docker.
        Path(target_path).write_bytes(b"fixture installed program, no credentials")

    def installs(self):
        return sum("npm install" in command for command in self.calls)

    async def test_cold_then_warm_checks_payload_and_actual_binary(self):
        first = await manager.install(self.environment, "codex", logs_dir=self.root / "logs")
        second = await manager.install(self.environment, "codex", logs_dir=self.root / "logs")
        self.assertFalse(first["cache_hit"])
        self.assertTrue(second["cache_hit"])
        self.assertEqual(self.installs(), 1)
        self.assertEqual(sum(command.endswith(" --version") for command in self.calls), 2)
        self.assertEqual(self.environment.upload_file.await_count, 1)
        record = self.root / "logs/harness.json"
        self.assertEqual(stat.S_IMODE(record.stat().st_mode), 0o600)
        self.assertEqual(json.loads(record.read_text())["actual_version"], "0.164.0")
        self.assertEqual(stat.S_IMODE((self.root / "cache").stat().st_mode), 0o700)
        home_links = [user for command, user in zip(self.calls, self.users) if 'mkdir -p "$HOME/.local/bin"' in command]
        self.assertEqual(home_links, [None, None])

    async def test_corruption_reinstalls_and_different_image_does_not_share_cache(self):
        first = await manager.install(self.environment, "codex")
        payload = self.root / "cache" / first["cache_key"] / "program.tar.gz"
        original = payload.read_bytes()
        payload.write_bytes(b"x" * len(original))  # Same size, wrong checksum.
        repaired = await manager.install(self.environment, "codex")
        self.assertFalse(repaired["cache_hit"])
        self.assertEqual(payload.read_bytes(), original)
        self.image_mock.return_value = "sha256:" + "b" * 64
        other = await manager.install(self.environment, "codex")
        self.assertFalse(other["cache_hit"])
        self.assertNotEqual(first["cache_key"], other["cache_key"])
        self.assertEqual(self.installs(), 3)

    async def test_version_mismatch_never_populates_cache(self):
        self.output = "codex-cli 0.163.0\n"
        with self.assertRaisesRegex(RuntimeError, "version mismatch"):
            await manager.install(self.environment, "codex")
        self.assertFalse(list((self.root / "cache").glob("*/manifest.json")))
        self.assertTrue(self.calls[-1].startswith("rm -f -- /tmp/search-swe-harness-"))

    async def test_warm_cache_reverifies_executable(self):
        await manager.install(self.environment, "codex")
        self.output = "codex-cli 0.163.0\n"
        with self.assertRaisesRegex(RuntimeError, "version mismatch"):
            await manager.install(self.environment, "codex")
        self.assertEqual(self.installs(), 1)

    async def test_cache_rejects_public_directory_and_symlink_payload(self):
        first = await manager.install(self.environment, "codex")
        payload = self.root / "cache" / first["cache_key"] / "program.tar.gz"
        payload.unlink()
        payload.symlink_to(self.root / "external")
        self.assertFalse(manager.valid_cache(payload.parent, first["cache_key"]))
        (self.root / "cache").chmod(0o755)
        with self.assertRaisesRegex(ValueError, "0700"):
            manager.cache_root()

    async def test_lock_serializes_same_entry(self):
        root = manager.cache_root()
        events = []
        async def worker(index):
            async with manager.cache_lock(root, "fixture"):
                events.append((index, "enter"))
                await asyncio.sleep(.02)
                events.append((index, "exit"))
        await asyncio.gather(worker(1), worker(2))
        self.assertEqual(events, [(1, "enter"), (1, "exit"), (2, "enter"), (2, "exit")])

    async def test_native_override_checks_binary_not_requested_version_attribute(self):
        agent = SimpleNamespace(_version="9.9.9", get_version_command=lambda: "native --version",
                                parse_version=lambda output: output.strip())
        self.output = "1.2.3\n"
        with self.assertRaisesRegex(RuntimeError, "version mismatch"):
            await manager.verify_native(agent, self.environment, "9.9.9")
        await manager.verify_native(agent, self.environment, "1.2.3")
        self.assertEqual(agent._version, "1.2.3")
        with self.assertRaisesRegex(ValueError, "no verifiable CLI"):
            await manager.verify_native(SimpleNamespace(), self.environment, "1.2.3")

    async def test_setup_failure_restores_original_network(self):
        from harbor.models.task.config import NetworkPolicy
        class Base:
            def __init__(self, version=None):
                self._version = version

            async def setup(self, environment):
                raise RuntimeError("install failed")
        class Agent(manager.ManagedHarness, Base):
            HARNESS_NAME = "codex"
        original = NetworkPolicy(network_mode="no-network")
        environment = SimpleNamespace(network_policy=original, set_network_policy=AsyncMock())
        with self.assertRaisesRegex(RuntimeError, "install failed"):
            await Agent().setup(environment)
        policies = environment.set_network_policy.call_args_list
        self.assertEqual(policies[0].args[0].network_mode.value, "allowlist")
        self.assertEqual(policies[-1].args[0], original)


if __name__ == "__main__":
    unittest.main()
