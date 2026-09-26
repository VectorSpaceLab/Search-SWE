import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest


SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location("check_release", SCRIPTS / "check_release.py")
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


class ReleasePackage(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)
        self.task = self.repo / "tasks" / "task-new"
        for name in ("environment", "tests", "data"):
            (self.task / name).mkdir(parents=True)
        for name in ("instruction.md", "environment/Dockerfile", "tests/Dockerfile", "tests/test.sh"):
            (self.task / name).write_text("fixture\n")
        for name in ("environment/docker-compose.yaml", "tests/docker-compose.yaml"):
            (self.task / name).write_text("services: {}\n")
        (self.task / "task.toml").write_text(
            '[task]\nname = "fixture/task-new"\nversion = "0.1"\n'
            '[verifier.env]\nOPENAI_BASE_URL = "${OPENAI_BASE_URL:-}"\n'
            'OPENAI_API_KEY = "${OPENAI_API_KEY:-}"\n'
        )
        (self.task / ".gitignore").write_text("/data/\n/models/\n")
        self.content = b"fixed data\n"
        self.entry = {
            "path": "data/corpus.jsonl", "size_bytes": len(self.content),
            "sha256": hashlib.sha256(self.content).hexdigest(),
            "source": {"repo_id": "search-swe/Search-SWE", "repo_type": "dataset",
                       "revision": "a" * 40, "filename": "tasks/task-new/corpus.jsonl"},
        }
        self.write_manifest()
        (self.task / self.entry["path"]).write_bytes(self.content)
        self.hf = self.root / "hf-data"
        self.hf_file = self.hf / "tasks/task-new/corpus.jsonl"
        self.hf_file.parent.mkdir(parents=True)
        self.hf_file.write_bytes(self.content)
        for name in ("README.md", "SOURCES.md", ".gitattributes"):
            (self.hf / name).write_text("fixture\n")
        record = {key: self.entry[key] for key in ("size_bytes", "sha256")}
        record["path"] = "tasks/task-new/corpus.jsonl"
        (self.hf / "manifest.json").write_text(json.dumps({"schema_version": 1, "files": [record]}))
        shutil.copytree(SCRIPTS, self.repo / "scripts", ignore=shutil.ignore_patterns("__pycache__", "tests"))

    def write_manifest(self):
        (self.task / "assets.json").write_text(json.dumps({"schema_version": 1, "files": [self.entry]}))

    def launcher_env(self):
        blocked = (
            "AGENT_", "VERIFIER_", "CONTAINER_", "TRAJECTORY_JUDGE_",
            "ANSWER_JUDGE_", "DEEPSEEK_API_KEY", "ZAI_API_KEY", "PI_THINKING",
            "ANTHROPIC_", "CLAUDE_", "AWS_BEARER_TOKEN_BEDROCK",
        )
        return {key: value for key, value in os.environ.items()
                if not key.startswith(blocked)}

    @staticmethod
    def flag_values(argv, flag):
        return [argv[index + 1] for index, value in enumerate(argv[:-1]) if value == flag]

    def test_valid_package_reports_unset_license_without_blocking_file_checks(self):
        errors, warnings = release.check_release(self.repo, self.hf, verify_data=True)
        self.assertEqual(errors, [])
        self.assertTrue(any("license" in warning for warning in warnings))

    def test_same_size_corruption_is_detected_by_checksum(self):
        self.hf_file.write_bytes(b"x" * len(self.content))
        errors, _ = release.check_release(self.repo, self.hf, verify_data=True)
        self.assertTrue(any("SHA-256 mismatch" in error for error in errors))

    def test_mutable_asset_revision_is_rejected(self):
        self.entry["source"]["revision"] = "main"
        self.write_manifest()
        errors, _ = release.check_release(self.repo)
        self.assertTrue(any("immutable commit" in error for error in errors))

    def test_unpublished_data_requires_explicit_local_staging_mode(self):
        self.entry["source"]["revision"] = None
        self.write_manifest()
        errors, _ = release.check_release(self.repo, self.hf, verify_data=True)
        self.assertTrue(any("immutable commit" in error for error in errors))
        errors, warnings = release.check_release(self.repo, self.hf, verify_data=True, allow_unpublished=True)
        self.assertEqual(errors, [])
        self.assertTrue(any("publish them" in warning for warning in warnings))
        self.entry["source"]["revision"] = "main"
        self.write_manifest()
        errors, _ = release.check_release(self.repo, self.hf, allow_unpublished=True)
        self.assertTrue(any("immutable commit" in error for error in errors))

    def test_staging_mode_still_rejects_corrupt_data(self):
        self.entry["source"]["revision"] = None
        self.write_manifest()
        self.hf_file.write_bytes(b"x" * len(self.content))
        errors, _ = release.check_release(self.repo, self.hf, verify_data=True, allow_unpublished=True)
        self.assertTrue(any("SHA-256 mismatch" in error for error in errors))

    def test_forced_tracked_data_is_rejected_even_when_ignored(self):
        subprocess.run(["git", "add", "-f", "tasks/task-new/data/corpus.jsonl"], cwd=self.repo, check=True)
        errors, _ = release.check_release(self.repo)
        self.assertTrue(any("runtime asset would enter Git" in error for error in errors))

    def test_hidden_or_unlisted_hf_input_is_rejected(self):
        (self.hf_file.parent / "hidden-labels.json").write_text("{}")
        errors, _ = release.check_release(self.repo, self.hf)
        self.assertTrue(any("unlisted task file" in error for error in errors))

    def test_new_task_automatically_appears_in_download_and_launch_commands(self):
        for script, args in (
            ("download_assets.py", ["--task", "all", "--dry-run"]),
            ("run_task.py", ["--task", "task-new", "--model", "example-model", "--dry-run"]),
        ):
            result = subprocess.run([sys.executable, str(self.repo / "scripts" / script), *args],
                                    cwd=self.root, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("task-new", result.stdout)

    def test_launcher_separates_agent_and_verifier_keys_without_putting_them_in_argv(self):
        (self.repo / ".env").write_text(
            "AGENT_MODEL=example-model\nAGENT_OPENAI_BASE_URL=https://agent.example/v1\n"
            "AGENT_OPENAI_API_KEY=fixture-agent-secret\n"
            "VERIFIER_OPENAI_BASE_URL=https://judge.example/v1\n"
            "VERIFIER_OPENAI_API_KEY=fixture-judge-secret\n"
        )
        bin_dir = self.root / "bin"
        bin_dir.mkdir()
        fake_harbor = bin_dir / "harbor"
        fake_harbor.write_text(
            f"#!{sys.executable}\nimport json, os, sys\n"
            "assert os.environ['AGENT_OPENAI_API_KEY'] == 'fixture-agent-secret'\n"
            "assert os.environ['VERIFIER_OPENAI_API_KEY'] == 'fixture-judge-secret'\n"
            "assert 'CODEX_AUTH_JSON_PATH' not in os.environ\n"
            "assert 'CODEX_FORCE_AUTH_JSON' not in os.environ\n"
            "print(json.dumps(sys.argv[1:]))\n"
        )
        fake_harbor.chmod(0o755)
        env = {key: value for key, value in os.environ.items()
               if not key.startswith(("AGENT_", "VERIFIER_", "CONTAINER_"))}
        env["PATH"] = str(bin_dir) + os.pathsep + env.get("PATH", "")
        env["CODEX_AUTH_JSON_PATH"] = "/unused/auth.json"
        env["CODEX_FORCE_AUTH_JSON"] = "1"
        result = subprocess.run([sys.executable, str(self.repo / "scripts/run_task.py"),
                                 "--task", "task-new"], cwd=self.root, env=env,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        output = result.stdout + result.stderr
        self.assertNotIn("fixture-agent-secret", output)
        self.assertNotIn("fixture-judge-secret", output)
        argv = json.loads(result.stdout.splitlines()[-1])
        self.assertIn("OPENAI_API_KEY=${AGENT_OPENAI_API_KEY}", argv)
        self.assertIn("OPENAI_API_KEY=${VERIFIER_OPENAI_API_KEY}", argv)

    def test_step_restriction_selects_gateway_and_model_host(self):
        (self.task / "task.toml").write_text(
            '[environment]\nnetwork_mode = "public"\n'
            '[agent]\nnetwork_mode = "public"\n'
            '[[steps]]\nname = "online"\n'
            '[[steps]]\nname = "offline"\n[steps.agent]\nnetwork_mode = "no-network"\n'
        )
        command = [sys.executable, str(self.repo / "scripts/run_task.py"), "--task", "task-new",
                   "--agent", "pi", "--model", "deepseek/deepseek-flash", "--dry-run"]
        result = subprocess.run(command, cwd=self.root, env=self.launcher_env(), capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        argv = shlex.split(result.stdout.splitlines()[-1])
        self.assertEqual(argv[argv.index("--env")+1], "scripts.harbor_environments:PhaseScopedDocker")
        self.assertEqual(self.flag_values(argv, "--allow-agent-host"), ["api.deepseek.com"])
        result = subprocess.run(command, cwd=self.root,
                                env={**self.launcher_env(), "CONTAINER_PROXY": "http://192.0.2.1:7890"},
                                capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("general proxy can bypass", result.stderr)

    def test_launcher_makes_repository_agents_importable(self):
        # A console script starts with its bin directory on sys.path, not cwd.
        # Import the real adapter in a new interpreter, not just inspect argv.
        bin_dir = self.root / "bin"
        bin_dir.mkdir()
        fake_harbor = bin_dir / "harbor"
        fake_harbor.write_text(
            f"#!{sys.executable}\n"
            "import importlib, json, os, sys\n"
            "from pathlib import Path\n"
            "module_name, class_name = sys.argv[sys.argv.index('--agent') + 1].split(':')\n"
            "module = importlib.import_module(module_name)\n"
            f"assert Path(module.__file__).resolve() == Path({str(self.repo / 'scripts/harbor_agents.py')!r})\n"
            "assert getattr(module, class_name).__module__ == module_name\n"
            f"assert os.environ['PYTHONPATH'] == {str(self.repo)!r} + os.environ['EXPECTED_PATH_SUFFIX']\n"
            "assert 'CODEX_AUTH_JSON_PATH' not in os.environ\n"
            "assert 'CODEX_FORCE_AUTH_JSON' not in os.environ\n"
            "print(json.dumps(sys.argv[1:]))\n"
        )
        fake_harbor.chmod(0o755)
        old_paths = os.pathsep.join((str(self.root / "existing-a"), str(self.root / "existing-b")))
        for agent, model in (("pi", "deepseek/deepseek-flash"),
                             ("codex", "example-model"),
                             ("claude-code", "claude-sonnet-4-6")):
            for existing in (None, "", old_paths):
                with self.subTest(agent=agent, pythonpath=existing):
                    env = self.launcher_env()
                    env.pop("PYTHONPATH", None)
                    if existing is not None:
                        env["PYTHONPATH"] = existing
                    env.update({
                        "PATH": str(bin_dir) + os.pathsep + env.get("PATH", ""),
                        "EXPECTED_PATH_SUFFIX": os.pathsep + existing if existing else "",
                        "AGENT_OPENAI_BASE_URL": "https://agent.example/v1",
                        "AGENT_OPENAI_API_KEY": "fixture-agent-secret",
                        "AGENT_ANTHROPIC_API_KEY": "fixture-anthropic-secret",
                        "DEEPSEEK_API_KEY": "fixture-provider-secret",
                        "VERIFIER_OPENAI_BASE_URL": "https://judge.example/v1",
                        "VERIFIER_OPENAI_API_KEY": "fixture-judge-secret",
                        "CODEX_AUTH_JSON_PATH": "/unused/auth.json",
                        "CODEX_FORCE_AUTH_JSON": "1",
                        # Real Harbor imports LiteLLM; keep this regression offline.
                        "LITELLM_LOCAL_MODEL_COST_MAP": "True",
                    })
                    result = subprocess.run(
                        [sys.executable, str(self.repo / "scripts/run_task.py"),
                         "--task", "task-new", "--agent", agent, "--model", model],
                        cwd=self.root, env=env, capture_output=True, text=True, timeout=60,
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)
                    for secret in ("fixture-agent-secret", "fixture-anthropic-secret",
                                   "fixture-provider-secret", "fixture-judge-secret"):
                        self.assertNotIn(secret, result.stdout + result.stderr)
                    argv = json.loads(result.stdout.splitlines()[-1])
                    self.assertEqual(argv[argv.index("-m") + 1], model)
                    self.assertIn("OPENAI_API_KEY=${VERIFIER_OPENAI_API_KEY}", argv)

    def test_codex_options_remain_supported(self):
        config = self.root / "codex.local.toml"
        config.write_text('model_provider = "fixture"\n')
        env = self.launcher_env()
        env["PI_THINKING"] = "extreme"
        result = subprocess.run(
            [sys.executable, str(self.repo / "scripts/run_task.py"),
             "--task", "task-new", "--agent", "codex", "--model", "example-model",
             "--reasoning-effort", "high", "--codex-config", str(config), "--dry-run"],
            cwd=self.root, env=env, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        argv = shlex.split(result.stdout.splitlines()[-1])
        self.assertIn("reasoning_effort=high", self.flag_values(argv, "--ak"))
        self.assertIn(f"config={config.resolve()}", self.flag_values(argv, "--ak"))
        self.assertIn("OPENAI_BASE_URL=${AGENT_OPENAI_BASE_URL}",
                      self.flag_values(argv, "--ae"))

    def test_launcher_bypasses_harbor_022_gpu_preflight_for_docker(self):
        for gpus, expected in ((0, []), (1, ["0"])):
            with self.subTest(gpus=gpus):
                (self.task / "task.toml").write_text(
                    '[task]\nname = "fixture/task-new"\nversion = "0.1"\n'
                    f'[environment]\ngpus = {gpus}\n'
                    '[verifier.env]\nOPENAI_BASE_URL = "${OPENAI_BASE_URL:-}"\n'
                    'OPENAI_API_KEY = "${OPENAI_API_KEY:-}"\n'
                )
                result = subprocess.run(
                    [sys.executable, str(self.repo / "scripts/run_task.py"),
                     "--task", "task-new", "--model", "example-model", "--dry-run"],
                    cwd=self.root, env=self.launcher_env(), capture_output=True, text=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                argv = shlex.split(result.stdout.splitlines()[-1])
                self.assertEqual(self.flag_values(argv, "--override-gpus"), expected)

    def test_launcher_builds_supported_pi_commands(self):
        for model, key, other_key in (
            ("deepseek/deepseek-flash", "DEEPSEEK_API_KEY", "ZAI_API_KEY"),
            ("zai/glm-5.3-flash", "ZAI_API_KEY", "DEEPSEEK_API_KEY"),
        ):
            with self.subTest(model=model):
                env = self.launcher_env()
                env["AGENT_REASONING_EFFORT"] = "codex-only"
                env["AGENT_CODEX_CONFIG"] = "missing-codex-config.toml"
                result = subprocess.run(
                    [sys.executable, str(self.repo / "scripts/run_task.py"),
                     "--task", "task-new", "--agent", "pi", "--model", model,
                     "--thinking", "xhigh", "--dry-run"],
                    cwd=self.root, env=env, capture_output=True, text=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                argv = shlex.split(result.stdout.splitlines()[-1])
                self.assertEqual(
                    argv[argv.index("--agent") + 1],
                    "scripts.harbor_agents:PreinstalledPi",
                )
                self.assertEqual(argv[argv.index("-m") + 1], model)
                self.assertIn("version=0.85.1", self.flag_values(argv, "--ak"))
                self.assertIn("thinking=xhigh", self.flag_values(argv, "--ak"))
                self.assertFalse(any(value.startswith(("reasoning_effort=", "config="))
                                     for value in self.flag_values(argv, "--ak")))
                agent_env = self.flag_values(argv, "--ae")
                self.assertIn(f"{key}=${{{key}}}", agent_env)
                self.assertFalse(any(value.startswith(f"{other_key}=") for value in agent_env))
                self.assertNotIn("OPENAI_BASE_URL=${AGENT_OPENAI_BASE_URL}", agent_env)
                self.assertNotIn("OPENAI_API_KEY=${AGENT_OPENAI_API_KEY}", agent_env)
                self.assertIn("OPENAI_API_KEY=${VERIFIER_OPENAI_API_KEY}",
                              self.flag_values(argv, "--verifier-env"))

    def test_launcher_builds_pinned_claude_code_command(self):
        env = self.launcher_env()
        env["AGENT_REASONING_EFFORT"] = "max"
        result = subprocess.run(
            [
                sys.executable,
                str(self.repo / "scripts/run_task.py"),
                "--task",
                "task-new",
                "--agent",
                "claude-code",
                "--model",
                "claude-sonnet-4-6",
                "--dry-run",
            ],
            cwd=self.root,
            env=env,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        argv = shlex.split(result.stdout.splitlines()[-1])
        self.assertEqual(
            argv[argv.index("--agent") + 1],
            "scripts.harbor_agents:PreinstalledClaudeCode",
        )
        self.assertEqual(argv[argv.index("-m") + 1], "claude-sonnet-4-6")
        self.assertIn("version=2.1.273", self.flag_values(argv, "--ak"))
        self.assertIn("reasoning_effort=max", self.flag_values(argv, "--ak"))
        self.assertEqual(
            self.flag_values(argv, "--ae"),
            ["ANTHROPIC_API_KEY=${AGENT_ANTHROPIC_API_KEY}"],
        )
        self.assertIn(
            "OPENAI_API_KEY=${VERIFIER_OPENAI_API_KEY}",
            self.flag_values(argv, "--verifier-env"),
        )

    def test_launcher_rejects_unsupported_pi_models_and_cross_agent_options(self):
        cases = (
            (["--agent", "pi", "--model", "plain-model"], "Supported Pi models"),
            (["--agent", "pi", "--model", "deepseek/"], "Supported Pi models"),
            (["--agent", "pi", "--model", "deepseek/unknown"], "Supported Pi models"),
            (["--agent", "pi", "--model", "unknown/model"], "Supported Pi models"),
            (["--agent", "pi", "--model", "deepseek/deepseek-flash",
              "--reasoning-effort", "high"], "--reasoning-effort is only valid"),
            (["--agent", "pi", "--model", "deepseek/deepseek-flash",
              "--codex-config", "missing.toml"], "--codex-config is only valid"),
            (["--agent", "codex", "--model", "example-model",
              "--thinking", "high"], "--thinking is only valid"),
            (["--agent", "claude-code", "--model", "claude-sonnet-4-6",
              "--thinking", "high"], "--thinking is only valid"),
            (["--agent", "claude-code", "--model", "claude-sonnet-4-6",
              "--codex-config", "missing.toml"], "--codex-config is only valid"),
            (["--agent", "claude-code", "--model", "claude-sonnet-4-6",
              "--reasoning-effort", "ultracode"], "Claude Code reasoning effort"),
        )
        for arguments, message in cases:
            with self.subTest(arguments=arguments):
                result = subprocess.run(
                    [sys.executable, str(self.repo / "scripts/run_task.py"),
                     "--task", "task-new", *arguments, "--dry-run"],
                    cwd=self.root, env=self.launcher_env(), capture_output=True, text=True,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(message, result.stderr)

    def test_pi_defaults_version_and_validates_environment_thinking(self):
        base = [sys.executable, str(self.repo / "scripts/run_task.py"),
                "--task", "task-new", "--agent", "pi",
                "--model", "deepseek/deepseek-flash", "--dry-run"]
        result = subprocess.run(base, cwd=self.root, env=self.launcher_env(),
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        argv = shlex.split(result.stdout.splitlines()[-1])
        self.assertIn("version=0.85.1", self.flag_values(argv, "--ak"))
        self.assertFalse(any(value.startswith("thinking=") for value in self.flag_values(argv, "--ak")))

        env = self.launcher_env()
        env["PI_THINKING"] = "high"
        result = subprocess.run(base, cwd=self.root, env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        argv = shlex.split(result.stdout.splitlines()[-1])
        self.assertIn("thinking=high", self.flag_values(argv, "--ak"))

        (self.repo / ".env").write_text("PI_THINKING=medium\n")
        result = subprocess.run(base, cwd=self.root, env=self.launcher_env(),
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        argv = shlex.split(result.stdout.splitlines()[-1])
        self.assertIn("thinking=medium", self.flag_values(argv, "--ak"))

        env["PI_THINKING"] = "extreme"
        result = subprocess.run(base, cwd=self.root, env=env, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("PI_THINKING", result.stderr)

    def test_pi_requires_only_selected_key_and_keeps_secrets_out_of_argv(self):
        provider_secret = "fixture provider $'\";` secret"
        (self.repo / ".env").write_text(
            "DEEPSEEK_API_KEY=fixture-file-secret\n"
            "VERIFIER_OPENAI_BASE_URL=https://judge.example/v1\n"
            "VERIFIER_OPENAI_API_KEY=fixture-judge-secret\n"
            "CONTAINER_PROXY=http://file-proxy-secret@example:7887\n"
        )
        bin_dir = self.root / "bin"
        bin_dir.mkdir()
        fake_harbor = bin_dir / "harbor"
        fake_harbor.write_text(
            f"#!{sys.executable}\nimport json, os, sys\n"
            f"assert os.environ['DEEPSEEK_API_KEY'] == {provider_secret!r}\n"
            "assert os.environ['CONTAINER_PROXY'] == 'http://shell-proxy-secret@example:7887'\n"
            "print(json.dumps(sys.argv[1:]))\n"
        )
        fake_harbor.chmod(0o755)
        env = self.launcher_env()
        env["PATH"] = str(bin_dir) + os.pathsep + env.get("PATH", "")
        env["DEEPSEEK_API_KEY"] = provider_secret
        env["CONTAINER_PROXY"] = "http://shell-proxy-secret@example:7887"
        result = subprocess.run(
            [sys.executable, str(self.repo / "scripts/run_task.py"),
             "--task", "task-new", "--agent", "pi",
             "--model", "deepseek/deepseek-flash"],
            cwd=self.root, env=env, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        output = result.stdout + result.stderr
        for secret in ("fixture-file-secret", provider_secret, "fixture-judge-secret",
                       "file-proxy-secret", "shell-proxy-secret"):
            self.assertNotIn(secret, output)
        argv = json.loads(result.stdout.splitlines()[-1])
        agent_env = self.flag_values(argv, "--ae")
        verifier_args = self.flag_values(argv, "--verifier-env")
        self.assertIn("DEEPSEEK_API_KEY=${DEEPSEEK_API_KEY}", agent_env)
        self.assertFalse(any(value.startswith("ZAI_API_KEY=") for value in agent_env))
        for name in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY"):
            self.assertIn(f"{name}=${{CONTAINER_PROXY}}", agent_env)
            self.assertIn(f"{name}=${{CONTAINER_PROXY}}", verifier_args)
        for name in ("no_proxy", "NO_PROXY"):
            self.assertIn(f"{name}=${{CONTAINER_NO_PROXY}}", agent_env)
            self.assertIn(f"{name}=${{CONTAINER_NO_PROXY}}", verifier_args)

        (self.repo / ".env").write_text(
            "VERIFIER_OPENAI_BASE_URL=https://judge.example/v1\n"
            "VERIFIER_OPENAI_API_KEY=fixture-judge-secret\n"
        )
        for model, key, other_key in (
            ("deepseek/deepseek-flash", "DEEPSEEK_API_KEY", "ZAI_API_KEY"),
            ("zai/glm-5.3-flash", "ZAI_API_KEY", "DEEPSEEK_API_KEY"),
        ):
            with self.subTest(missing=key):
                missing_env = self.launcher_env()
                missing_env[other_key] = "unselected-provider-secret"
                result = subprocess.run(
                    [sys.executable, str(self.repo / "scripts/run_task.py"),
                     "--task", "task-new", "--agent", "pi", "--model", model],
                    cwd=self.root, env=missing_env, capture_output=True, text=True,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(key, result.stderr)
                self.assertNotIn(other_key, result.stderr)

    def test_claude_requires_namespaced_key_and_scrubs_host_auth(self):
        agent_secret = "fixture-anthropic-agent-secret"
        (self.repo / ".env").write_text(
            f"AGENT_ANTHROPIC_API_KEY={agent_secret}\n"
            "VERIFIER_OPENAI_BASE_URL=https://judge.example/v1\n"
            "VERIFIER_OPENAI_API_KEY=fixture-judge-secret\n"
        )
        bin_dir = self.root / "bin"
        bin_dir.mkdir()
        fake_harbor = bin_dir / "harbor"
        scrubbed = (
            "ANTHROPIC_API_KEY",
            "ANTHROPIC_AUTH_TOKEN",
            "ANTHROPIC_BASE_URL",
            "CLAUDE_CODE_OAUTH_TOKEN",
            "CLAUDE_FORCE_OAUTH",
            "CLAUDE_CODE_USE_BEDROCK",
            "CLAUDE_CODE_USE_VERTEX",
            "AWS_BEARER_TOKEN_BEDROCK",
        )
        fake_harbor.write_text(
            f"#!{sys.executable}\nimport json, os, sys\n"
            f"assert os.environ['AGENT_ANTHROPIC_API_KEY'] == {agent_secret!r}\n"
            f"assert not ({set(scrubbed)!r} & os.environ.keys())\n"
            "print(json.dumps(sys.argv[1:]))\n"
        )
        fake_harbor.chmod(0o755)
        env = self.launcher_env()
        env["PATH"] = str(bin_dir) + os.pathsep + env.get("PATH", "")
        for name in scrubbed:
            env[name] = f"untrusted-{name.lower()}"

        result = subprocess.run(
            [
                sys.executable,
                str(self.repo / "scripts/run_task.py"),
                "--task",
                "task-new",
                "--agent",
                "claude-code",
                "--model",
                "claude-sonnet-4-6",
            ],
            cwd=self.root,
            env=env,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        output = result.stdout + result.stderr
        self.assertNotIn(agent_secret, output)
        self.assertNotIn("untrusted-", output)
        argv = json.loads(result.stdout.splitlines()[-1])
        self.assertIn(
            "ANTHROPIC_API_KEY=${AGENT_ANTHROPIC_API_KEY}",
            self.flag_values(argv, "--ae"),
        )

        (self.repo / ".env").write_text(
            "VERIFIER_OPENAI_BASE_URL=https://judge.example/v1\n"
            "VERIFIER_OPENAI_API_KEY=fixture-judge-secret\n"
        )
        result = subprocess.run(
            [
                sys.executable,
                str(self.repo / "scripts/run_task.py"),
                "--task",
                "task-new",
                "--agent",
                "claude-code",
                "--model",
                "claude-sonnet-4-6",
            ],
            cwd=self.root,
            env=self.launcher_env(),
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("AGENT_ANTHROPIC_API_KEY", result.stderr)

    def test_launcher_requires_only_the_selected_tasks_judge_groups(self):
        bin_dir = self.root / "bin"
        bin_dir.mkdir()
        fake_harbor = bin_dir / "harbor"
        fake_harbor.write_text(f"#!{sys.executable}\nimport json, sys\nprint(json.dumps(sys.argv[1:]))\n")
        fake_harbor.chmod(0o755)
        env = {key: value for key, value in os.environ.items()
               if not key.startswith(("AGENT_", "VERIFIER_", "CONTAINER_", "TRAJECTORY_JUDGE_", "ANSWER_JUDGE_"))}
        env["PATH"] = str(bin_dir) + os.pathsep + env.get("PATH", "")
        agent = "AGENT_MODEL=fixture-model\nAGENT_OPENAI_BASE_URL=https://agent.example/v1\nAGENT_OPENAI_API_KEY=fixture-agent-key\n"
        trajectory = "VERIFIER_OPENAI_BASE_URL=https://audit.example/v1\nVERIFIER_OPENAI_API_KEY=fixture-audit-key\n"
        answer = "ANSWER_JUDGE_MODEL_NAME=fixture-answer-model\nANSWER_JUDGE_BASE_URL=https://answer.example/v1\nANSWER_JUDGE_API_KEY=fixture-answer-key\n"
        trajectory_keys = ["OPENAI_BASE_URL", "OPENAI_API_KEY"]
        answer_keys = ["ANSWER_JUDGE_MODEL_NAME", "ANSWER_JUDGE_BASE_URL", "ANSWER_JUDGE_API_KEY"]
        for keys, values, success in [
            ([], agent, True),
            (trajectory_keys, agent + trajectory, True),
            (trajectory_keys + answer_keys, agent + trajectory, False),
            (trajectory_keys + answer_keys, agent + trajectory + answer, True),
        ]:
            with self.subTest(keys=keys, success=success):
                (self.task / "task.toml").write_text(
                    '[task]\nname = "fixture/task-new"\nversion = "0.1"\n[verifier.env]\n'
                    + ''.join(f'{key} = "${{{key}:-}}"\n' for key in keys)
                )
                (self.repo / ".env").write_text(values)
                result = subprocess.run([sys.executable, str(self.repo / "scripts/run_task.py"), "--task", "task-new"],
                                        cwd=self.root, env=env, capture_output=True, text=True)
                if success:
                    self.assertEqual(result.returncode, 0, result.stderr)
                    argv = json.loads(result.stdout.splitlines()[-1])
                    self.assertEqual("OPENAI_API_KEY=${VERIFIER_OPENAI_API_KEY}" in argv, bool(keys))
                    output = result.stdout + result.stderr
                    for secret in ("fixture-agent-key", "fixture-audit-key", "fixture-answer-key"):
                        self.assertNotIn(secret, output)
                else:
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("ANSWER_JUDGE_API_KEY", result.stderr)


if __name__ == "__main__":
    unittest.main()
