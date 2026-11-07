"""Native Harbor discovery, launch contracts and credential/network isolation."""

import asyncio
from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
from pathlib import Path
import shlex
import stat
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from harbor.agents.factory import AgentFactory
from harbor.agents.installed.antigravity_cli import AntigravityCli
from harbor.models.job.config import JobConfig
from harbor.models.task.config import NetworkMode, NetworkPolicy
from harbor.models.trial.config import AgentConfig
from search_swe import harbor_native
from search_swe.cli import main, parser
from search_swe.configuration import Setting, resolve_setting, saved_setting
from scripts.evaluation import run_task
from scripts.evaluation.native_agents import NativeAgent, agent_environment


class FixtureAgent:
    SUPPORTS_ATIF = True

    def __init__(self, *, extra_env, fail=False, **kwargs):
        self.extra_env = extra_env
        self.fail = fail
        self.initial_key = os.environ.get("OPENROUTER_API_KEY")
        self.initial_judge = os.environ.get("VERIFIER_OPENAI_API_KEY")
        self.initial_pat = os.environ.get("SNOWFLAKE_PAT")

    async def setup(self, environment):
        self.setup_hosts = environment.network_policy.allowed_hosts
        self.setup_key = os.environ.get("OPENROUTER_API_KEY")
        if self.fail:
            raise RuntimeError("fixture installation failure")

    async def run(self, *args, **kwargs):
        return os.environ.get("OPENROUTER_API_KEY"), os.environ.get("VERIFIER_OPENAI_API_KEY")


class NativeAgents(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def config(self, value):
        path = self.root / "native.json"
        path.write_text(json.dumps(value))
        return str(path)

    def test_catalog_matches_actual_factory_and_preserves_capabilities(self):
        expected = {name.value for name in AgentFactory._AGENT_MAP}
        self.assertEqual(set(harbor_native.names()), expected)
        self.assertIn("antigravity-cli", expected)
        with patch("search_swe.cli.find_repo", side_effect=ValueError("no checkout")), \
                redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(["agents", "--json"]), 0)
        rows = json.loads(output.getvalue())
        self.assertEqual({item["name"] for item in rows}, expected)
        self.assertFalse(next(item for item in rows if item["name"] == "aider")["native_atif"])
        for name in expected:
            with self.subTest(agent=name):
                args = parser().parse_args(["configure", "--agent", name, "--provider", "native", "--yes"])
                setting = resolve_setting(Setting(), args)
                self.assertEqual(setting.agent, name)
                self.assertEqual(setting.provider, "native")
                self.assertEqual(saved_setting(setting.values()), setting)

    def test_agent_route_and_credential_selection(self):
        setting = Setting("antigravity-cli", "native", "gemini/gemini-2.5-flash", "default").validate()
        self.assertEqual(setting.required({}), {"AGENT_GEMINI_API_KEY"})
        self.assertIn("--native", setting.flags())
        self.assertNotIn("--reasoning-effort", setting.flags())
        self.assertEqual(Setting("nop", "native", "", "default").validate().required({}), set())
        with self.assertRaisesRegex(ValueError, "Unsupported"):
            Setting("antigravity-cli", "openrouter", "google/model", "default").validate()
        plan = harbor_native.plan("aider", "openrouter/vendor/model", {"OPENROUTER_API_KEY": "submission-only"})
        self.assertEqual(plan["env"], {"OPENROUTER_API_KEY": "${AGENT_OPENROUTER_API_KEY}"})
        self.assertEqual(plan["required"], {"AGENT_OPENROUTER_API_KEY"})
        updater = "antigravity-cli-auto-updater-974169037036.us-central1.run.app"
        antigravity = harbor_native.plan("antigravity-cli", "gemini/model", {})
        self.assertIn(updater, antigravity["setup_hosts"])
        self.assertNotIn(updater, antigravity["hosts"])
        self.assertNotIn(updater, plan["setup_hosts"])
        cursor = harbor_native.plan('cursor-cli', '', {})
        self.assertIn('api2.cursor.sh', cursor['hosts'])
        self.assertIn('api2.cursor.sh', cursor['setup_hosts'])

    def test_native_provider_inference_matches_harbor_for_bare_names_and_aliases(self):
        for model, variable, host in (
            ("gpt-4o", "AGENT_OPENAI_API_KEY", "api.openai.com"),
            ("claude-sonnet-4-6", "AGENT_ANTHROPIC_API_KEY", "api.anthropic.com"),
            ("ai21_chat/jamba-large", "AGENT_AI21_API_KEY", None),
            ("litellm_proxy/example", "AGENT_OPENAI_API_KEY", "api.openai.com"),
        ):
            with self.subTest(model=model):
                plan = harbor_native.plan("aider", model, {variable: "fixture-agent"})
                self.assertEqual(plan["required"], {variable})
                self.assertEqual(plan["env"][variable.removeprefix("AGENT_")], "${" + variable + "}")
                if host:
                    self.assertIn(host, plan["hosts"])
        custom = harbor_native.plan("aider", "unlisted_provider/model", {
            "AGENT_UNLISTED_PROVIDER_BASE_URL": "https://models.example/v1"})
        self.assertEqual(custom["hosts"], ["models.example"])

    def test_grok_byok_matches_the_actual_native_provider_contract(self):
        import tomllib
        from harbor.agents.installed.grok_build import GrokBuild
        for provider, native in GrokBuild._PROVIDERS.items():
            with self.subTest(provider=provider):
                model = provider + "/vendor/model"
                key = native['env_key']
                plan = harbor_native.plan('grok-build', model, {'AGENT_' + key: 'fixture-byok'})
                self.assertEqual(plan['required'], {'AGENT_' + key})
                self.assertEqual(plan['env'], {key: '${AGENT_' + key + '}'})
                agent = NativeAgent(search_swe_native_name='grok-build', logs_dir=self.root,
                                    model_name=model, extra_env={key: 'fixture-byok'})
                configured = tomllib.loads(agent._build_config_toml())['model']['vendor/model']
                self.assertEqual(configured['env_key'], key)
                self.assertEqual(configured['base_url'], native['base_url'])
                self.assertIn(native['base_url'].split('/')[2], plan['hosts'])
                self.assertNotIn('api.x.ai', plan['hosts'])

    def test_junie_byok_aliases_and_credentials_match_native_auth(self):
        cases = (('anthropic', 'ANTHROPIC_API_KEY', 'JUNIE_ANTHROPIC_API_KEY', 'api.anthropic.com'),
                 ('claude', 'JUNIE_ANTHROPIC_API_KEY', 'JUNIE_ANTHROPIC_API_KEY', 'api.anthropic.com'),
                 ('gpt', 'OPENAI_API_KEY', 'JUNIE_OPENAI_API_KEY', 'api.openai.com'),
                 ('gemini', 'GEMINI_API_KEY', 'JUNIE_GOOGLE_API_KEY', 'generativelanguage.googleapis.com'),
                 ('grok', 'XAI_API_KEY', 'JUNIE_GROK_API_KEY', 'api.x.ai'),
                 ('openrouter', 'OPENROUTER_API_KEY', 'JUNIE_OPENROUTER_API_KEY', 'openrouter.ai'))
        for provider, supplied, native_key, host in cases:
            with self.subTest(provider=provider):
                model = provider + '/vendor/model'
                plan = harbor_native.plan('junie', model, {'AGENT_' + supplied: 'fixture-byok'})
                self.assertEqual(plan['required'], {'AGENT_' + supplied})
                self.assertEqual(plan['env'], {supplied: '${AGENT_' + supplied + '}'})
                agent = NativeAgent(search_swe_native_name='junie', logs_dir=self.root,
                                    model_name=model, extra_env={supplied: 'fixture-byok'})
                with agent_environment({}):
                    auth = agent._build_auth_env(agent._resolve_provider())
                self.assertEqual(auth[native_key], 'fixture-byok')
                self.assertNotIn('JUNIE_API_KEY', auth)
                self.assertIn(host, plan['hosts'])
        with self.assertRaisesRegex(ValueError, 'Junie BYOK provider'):
            harbor_native.plan('junie', 'unsupported/model', {})

    def test_vibe_generic_uses_selected_provider_key_and_explicit_endpoint(self):
        import tomllib
        path = self.config({'kwargs': {'backend': 'generic'}})
        for provider, key, endpoint in (
                ('openai', 'OPENAI_API_KEY', 'https://api.openai.com/v1'),
                ('openrouter', 'OPENROUTER_API_KEY', 'https://openrouter.ai/api/v1')):
            with self.subTest(provider=provider):
                source_env = {'AGENT_' + key: 'fixture-byok'}
                if provider == 'openrouter':
                    source_env['AGENT_OPENAI_BASE_URL'] = 'https://unrelated.example/v1'
                model = provider + '/vendor/model'
                plan = harbor_native.plan('vibe', model, source_env, path)
                self.assertEqual(plan['required'], {'AGENT_' + key})
                self.assertEqual(plan['env'], {'OPENAI_API_KEY': '${AGENT_' + key + '}', 'VIBE_API_BASE': endpoint})
                agent = NativeAgent(search_swe_native_name='vibe', logs_dir=self.root,
                                    model_name=model, backend='generic',
                                    extra_env={'OPENAI_API_KEY': 'fixture-byok', 'VIBE_API_BASE': endpoint})
                with agent_environment({}):
                    self.assertEqual(agent._get_backend_and_key_env(), ('generic', 'OPENAI_API_KEY'))
                    config = tomllib.loads(agent._build_config_toml())
                self.assertIn(endpoint, str(config))
                self.assertEqual(plan['hosts'], [endpoint.split('/')[2]])
        override = harbor_native.plan('vibe', 'openrouter/vendor/model', {
            'AGENT_OPENROUTER_API_KEY': 'fixture-byok',
            'AGENT_OPENROUTER_BASE_URL': 'https://router.example/v1'}, path)
        self.assertEqual(override['env']['VIBE_API_BASE'], '${AGENT_OPENROUTER_BASE_URL}')
        self.assertEqual(override['hosts'], ['router.example'])

    def test_service_default_auth_and_explicit_native_overrides_are_preserved(self):
        for name, model, key in (('grok-build', 'grok-code-fast-1', 'XAI_API_KEY'),
                                 ('junie', 'sonnet', 'JUNIE_API_KEY'),
                                 ('vibe', 'devstral-small-latest', 'MISTRAL_API_KEY')):
            with self.subTest(agent=name):
                plan = harbor_native.plan(name, model, {'AGENT_OPENAI_BASE_URL': 'https://unrelated.example/v1'})
                self.assertEqual(plan['required'], {'AGENT_' + key})
                self.assertEqual(plan['env'][key], '${AGENT_' + key + '}')
                self.assertNotIn('unrelated.example', plan['hosts'])
        path = self.config({'env': {'JUNIE_ANTHROPIC_API_KEY': '${AGENT_PRIVATE_KEY}'},
                            'extra_allowed_hosts': ['custom.example']})
        plan = harbor_native.plan('junie', 'anthropic/sonnet', {}, path)
        self.assertEqual(plan['env'], {'JUNIE_ANTHROPIC_API_KEY': '${AGENT_PRIVATE_KEY}'})
        self.assertEqual(plan['required'], {'AGENT_PRIVATE_KEY'})
        self.assertIn('custom.example', plan['hosts'])

    def test_native_model_can_be_cleared_in_scripted_settings(self):
        current = Setting("antigravity-cli", "native", "gemini/gemini-2.5-flash", "default")
        args = parser().parse_args(["configure", "--model", "", "--yes"])
        setting = resolve_setting(current, args)
        self.assertEqual(setting.model, "")
        self.assertEqual(saved_setting(setting.values()).model, "")
        flags = setting.flags()
        self.assertEqual(flags[flags.index("--model") + 1], "")
        pi = resolve_setting(Setting("pi", "native", "openai/gpt-4o", "default"), args)
        self.assertEqual(saved_setting(pi.values()).model, "")
        with self.assertRaisesRegex(ValueError, "model ID"):
            resolve_setting(Setting(), args)

    def test_native_atif_compatibility_is_checked_per_task_and_route(self):
        task = {"task": {"name": "search-swe/audited-task"}, "artifacts": ["/logs/agent/trajectory.json"]}
        for name in ("aider",):
            with self.subTest(agent=name), self.assertRaisesRegex(ValueError, "requires an ATIF"):
                harbor_native.check_trajectory_support(name, True, task)
            harbor_native.check_trajectory_support(name, True, {"artifacts": ["/app"]})
        for name in ("codex", "claude-code", "gemini-cli", "antigravity-cli", "pi", "oracle", "nop"):
            harbor_native.check_trajectory_support(name, True, task)
        harbor_native.check_trajectory_support("pi", False, task)

    def test_native_backend_checks_artifacts_and_honors_an_explicit_empty_model(self):
        task = self.root / "tasks/example-search"
        task.mkdir(parents=True)
        config = ('schema_version="1.4"\n[task]\nname="search-swe/example-search"\nversion="1.0.0"\n'
                  '[environment]\nnetwork_mode="no-network"\ncpus=1\nmemory_mb=1024\nstorage_mb=1024\n'
                  '[agent]\nnetwork_mode="no-network"\n[verifier]\nnetwork_mode="no-network"\n')
        toml = task / "task.toml"
        toml.write_text('artifacts=["/logs/agent/trajectory.json"]\n' + config)
        common = ["run_task.py", "--task-path", "tasks/example-search", "--native", "--no-env-file"]
        with patch.object(run_task, "REPO", self.root), patch.dict(os.environ, {}, clear=True):
            for mode in ("--check", "--dry-run"):
                with patch.object(sys, "argv", [*common, "--agent", "aider", "--model", "openai/gpt-4o", mode]), \
                        redirect_stderr(io.StringIO()) as error, self.assertRaises(SystemExit):
                    run_task.main()
                self.assertIn("requires an ATIF", error.getvalue())
            toml.write_text(config)
            with patch.dict(os.environ, {"AGENT_OPENAI_API_KEY": "fixture-agent"}), \
                    patch.object(sys, "argv", [*common, "--agent", "pi", "--model", "openai/gpt-4o", "--check"]), \
                    redirect_stdout(io.StringIO()):
                self.assertEqual(run_task.main(), 0)
            with patch.dict(os.environ, {"AGENT_MODEL": "openai/old-model"}), \
                    patch.object(sys, "argv", [*common, "--agent", "nop", "--model", "", "--dry-run"]), \
                    redirect_stdout(io.StringIO()) as output:
                self.assertEqual(run_task.main(), 0)
                self.assertNotIn("-m", shlex.split(output.getvalue().splitlines()[-1]))

    def test_native_auth_files_are_owned_by_the_agent_and_failures_are_checked(self):
        async def exercise(fail):
            policy = NetworkPolicy(network_mode="public")
            calls = []
            async def execute(command, **kwargs):
                calls.append((command, kwargs))
                return SimpleNamespace(return_code=1 if fail and command.startswith("chown ") else 0,
                                       stdout="10001\n" if command == "id -u" else "", stderr="fixture permission failure" if fail else "")
            environment = SimpleNamespace(network_policy=policy, exec=execute, upload_file=AsyncMock())
            target = "/home/submission/.config/native/auth.json"
            with patch.object(harbor_native, "agent_class", return_value=FixtureAgent):
                agent = NativeAgent(search_swe_native_name="aider", extra_env={},
                                    search_swe_files=[{"source": str(self.root / "auth.json"), "target": target}])
                if fail:
                    with self.assertRaisesRegex(RuntimeError, "permission failure"):
                        await agent.setup(environment)
                else:
                    await agent.setup(environment)
                    self.assertEqual(calls[-1], (f"chown 10001 -- {target} && chmod 600 -- {target}", {"user": "root"}))
                environment.upload_file.assert_awaited_once()
        for fail in (False, True):
            asyncio.run(exercise(fail))

    def test_host_auth_selectors_cannot_override_the_selected_native_route(self):
        inherited = {"CLAUDE_CODE_USE_BEDROCK": "1", "CLAUDE_CODE_USE_VERTEX": "1",
                     "AWS_PROFILE": "unrelated-host-profile", "AWS_CONFIG_FILE": "/host/aws-config",
                     "GEMINI_FORCE_OAUTH": "1", "CODEX_FORCE_AUTH_JSON": "1",
                     "GOOGLE_APPLICATION_CREDENTIALS": "/host/adc.json", "CLOUDSDK_CONFIG": "/host/gcloud",
                     "VIBE_BACKEND": "generic", "VIBE_API_BASE": "https://unrelated.example/v1",
                     "VIBE_API_KEY_ENV": "UNRELATED_TOKEN"}
        with patch.dict(os.environ, inherited):
            agent = NativeAgent(search_swe_native_name="claude-code", logs_dir=self.root,
                                model_name="claude-sonnet-4-6", extra_env={"ANTHROPIC_API_KEY": "fixture-agent"})
            with agent_environment(agent.extra_env):
                self.assertTrue(set(inherited).isdisjoint(os.environ))
                self.assertEqual(agent.model_connection.provider, "anthropic")
                self.assertEqual(agent._resolve_auth_env()["ANTHROPIC_API_KEY"], "fixture-agent")
            explicit = {"CLAUDE_CODE_USE_BEDROCK": "1", "AWS_PROFILE": "selected-agent-profile"}
            with agent_environment(explicit):
                self.assertEqual(os.environ["AWS_PROFILE"], "selected-agent-profile")
                self.assertEqual(os.environ["CLAUDE_CODE_USE_BEDROCK"], "1")
            for name, value in inherited.items():
                self.assertEqual(os.environ[name], value)

    def test_configuration_references_files_and_endpoint_overrides(self):
        path = self.config({"env": {"AGY_ADC_AUTH": "true", "GOOGLE_APPLICATION_CREDENTIALS": "/root/adc.json"},
                            "files": {"${AGENT_ADC_FILE}": "/root/adc.json"},
                            "extra_allowed_hosts": ["oauth2.googleapis.com"], "kwargs": {"version": "1.2.3"}})
        plan = harbor_native.plan("antigravity-cli", "gemini/model", {}, path)
        self.assertEqual(plan["required"], {"AGENT_ADC_FILE"})
        self.assertEqual(plan["kwargs"], {"version": "1.2.3"})
        self.assertIn("oauth2.googleapis.com", plan["hosts"])
        plan = harbor_native.plan("antigravity-cli", "gemini/model", {"AGENT_GOOGLE_GEMINI_BASE_URL": "https://models.example/v1"})
        self.assertEqual(plan["hosts"], ["models.example"])
        self.assertEqual(plan["env"]["GOOGLE_GEMINI_BASE_URL"], "${AGENT_GOOGLE_GEMINI_BASE_URL}")

    def test_bad_configuration_fails_without_exposing_values(self):
        for value in ({"tasks": []}, {"kwargs": {"extra_env": {}}}, {"env": {"GEMINI_API_KEY": "fixture-secret"}},
                      {"env": {"OPENROUTER_API_KEY": "${OPENROUTER_API_KEY}"}},
                      {"extra_allowed_hosts": ["*.example.com"]}, {"setup_hosts": ["https://example.com"]},
                      {"files": {"${AGENT_FILE}": "/root/../app/private"}}):
            with self.subTest(value=value), self.assertRaises(ValueError) as caught:
                harbor_native.load_options(self.config(value))
            self.assertNotIn("fixture-secret", str(caught.exception))

    def test_actual_harbor_factory_constructs_antigravity(self):
        with patch.dict(os.environ, {"AGENT_GEMINI_API_KEY": "fixture-agent", "VERIFIER_OPENAI_API_KEY": "fixture-judge"}):
            config = AgentConfig(import_path="scripts.evaluation.native_agents:NativeAgent", model_name="gemini/gemini-2.5-flash",
                                 env={"GEMINI_API_KEY": "${AGENT_GEMINI_API_KEY}"},
                                 kwargs={"search_swe_native_name": "antigravity-cli"})
            agent = AgentFactory.create_agent_from_config(config, logs_dir=self.root)
            self.assertIsInstance(agent, AntigravityCli)
            self.assertTrue(agent.SUPPORTS_ATIF)
            self.assertEqual(agent.extra_env["GEMINI_API_KEY"], "fixture-agent")
            self.assertEqual(os.environ["VERIFIER_OPENAI_API_KEY"], "fixture-judge")

    def test_native_selection_on_an_older_checkout_reports_the_update(self):
        (self.root / 'pyproject.toml').write_text('[project]\nname="search-swe"\nversion="0.3.0"\n')
        (self.root / 'scripts/evaluation').mkdir(parents=True)
        (self.root / 'scripts/evaluation/run_task.py').touch()
        with patch('search_swe.cli.find_repo', return_value=self.root), \
                redirect_stderr(io.StringIO()) as error:
            code = main(['configure', '--agent', 'antigravity-cli', '--dry-run'])
        self.assertEqual(code, 1)
        self.assertIn('search-swe update', error.getvalue())
        self.assertFalse((self.root / '.env').exists())

    def test_explicit_empty_native_key_can_select_an_unauthenticated_endpoint(self):
        path = self.config({'env': {'OPENAI_API_KEY': '', 'OPENAI_BASE_URL': 'https://models.example/v1'}})
        plan = harbor_native.plan('aider', 'openai/model', {}, path)
        self.assertEqual(plan['required'], set())
        self.assertEqual(plan['hosts'], ['models.example'])

    def test_native_wizard_keeps_the_saved_effort_for_the_same_setting(self):
        from search_swe import wizard
        current = Setting('antigravity-cli', 'native', 'gemini/gemini-2.5-flash', 'high')
        args = parser().parse_args(['configure', '--agent', current.agent, '--provider', 'native', '--model', current.model])
        with patch.object(wizard, 'ask', return_value=''), redirect_stdout(io.StringIO()):
            self.assertEqual(wizard.select_setting(current, args), current)

    def test_install_and_run_restore_network_and_host_secrets_on_failure(self):
        async def exercise(fail):
            original = NetworkPolicy(network_mode=NetworkMode.ALLOWLIST, allowed_hosts=["task.example"])
            environment = SimpleNamespace(network_policy=original, exec=AsyncMock(), upload_file=AsyncMock())
            async def set_policy(policy):
                environment.network_policy = policy
            environment.set_network_policy = AsyncMock(side_effect=set_policy)
            with patch.dict(os.environ, {"OPENROUTER_API_KEY": "submission-private", "VERIFIER_OPENAI_API_KEY": "judge-private", "SNOWFLAKE_PAT": "unrelated-private"}), \
                    patch.object(harbor_native, "agent_class", return_value=FixtureAgent):
                agent = NativeAgent(search_swe_native_name="aider", search_swe_setup_hosts=["packages.example"],
                                    extra_env={"OPENROUTER_API_KEY": "agent-private"}, fail=fail)
                self.assertEqual(agent.initial_key, "agent-private")
                self.assertIsNone(agent.initial_judge)
                self.assertIsNone(agent.initial_pat)
                if fail:
                    with self.assertRaisesRegex(RuntimeError, "installation failure"):
                        await agent.setup(environment)
                else:
                    await agent.setup(environment)
                    self.assertEqual(await agent.run("instruction", environment, None), ("agent-private", None))
                self.assertIn("packages.example", agent.setup_hosts)
                self.assertEqual(environment.network_policy, original)
                self.assertEqual(os.environ["OPENROUTER_API_KEY"], "submission-private")
                self.assertEqual(os.environ["VERIFIER_OPENAI_API_KEY"], "judge-private")
        for fail in (False, True):
            asyncio.run(exercise(fail))

    def test_generated_job_keeps_kwargs_private_and_oracle_native(self):
        for name in harbor_native.names():
            with self.subTest(agent=name):
                plan = harbor_native.plan(name, "openai/model", {})
                plan["kwargs"]["config"] = {"opaque": "fixture-private-configuration"}
                command = ["harbor", "run", "--agent", name, "-m", "openai/model", "--n-attempts", "1"]
                with run_task.native_job(command, name, "openai/model", plan, {}) as argv:
                    path = Path(argv[argv.index("--config") + 1])
                    self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
                    self.assertNotIn("fixture-private-configuration", " ".join(argv))
                    self.assertNotIn("--agent", argv)
                    job = JobConfig.model_validate_json(path.read_text())
                    self.assertEqual(job.agents[0].model_name, "openai/model")
                    if name in ("oracle", "nop"):
                        self.assertEqual(job.agents[0].name, name)
                    else:
                        self.assertEqual(job.agents[0].kwargs["search_swe_native_name"], name)
                self.assertFalse(path.exists())

    def test_each_registered_agent_reaches_native_launcher_preview(self):
        task = self.root / "tasks/example-search"
        task.mkdir(parents=True)
        (task / "task.toml").write_text(
            'schema_version="1.4"\n[task]\nname="search-swe/example-search"\nversion="1.0.0"\n'
            '[environment]\nnetwork_mode="no-network"\ncpus=1\nmemory_mb=1024\nstorage_mb=1024\n'
            '[agent]\nnetwork_mode="no-network"\n[verifier]\nnetwork_mode="no-network"\n')
        for name in harbor_native.names():
            with self.subTest(agent=name), patch.object(run_task, "REPO", self.root), \
                    patch.dict(os.environ, {}, clear=True), redirect_stdout(io.StringIO()) as output, redirect_stderr(io.StringIO()):
                argv = ["run_task.py", "--task-path", "tasks/example-search", "--agent", name, "--native", "--no-env-file", "--dry-run"]
                with patch.object(sys, "argv", argv):
                    self.assertEqual(run_task.main(), 0)
                self.assertIn("Native agent config:", output.getvalue())


if __name__ == "__main__":
    unittest.main()
