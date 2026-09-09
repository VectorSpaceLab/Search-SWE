import hashlib
import importlib.util
import json
import os
from pathlib import Path
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
        (self.task / "task.toml").write_text('[task]\nname = "task-new"\nversion = "0.1"\n')
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
            "print(json.dumps(sys.argv[1:]))\n"
        )
        fake_harbor.chmod(0o755)
        env = {key: value for key, value in os.environ.items()
               if not key.startswith(("AGENT_", "VERIFIER_", "CONTAINER_"))}
        env["PATH"] = str(bin_dir) + os.pathsep + env.get("PATH", "")
        env["CODEX_AUTH_JSON_PATH"] = "/unused/auth.json"
        result = subprocess.run([sys.executable, str(self.repo / "scripts/run_task.py"),
                                 "--task", "task-new"], cwd=self.root, env=env,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("fixture-agent-secret", result.stdout)
        self.assertNotIn("fixture-judge-secret", result.stdout)
        argv = json.loads(result.stdout.splitlines()[-1])
        self.assertIn("OPENAI_API_KEY=${AGENT_OPENAI_API_KEY}", argv)
        self.assertIn("OPENAI_API_KEY=${VERIFIER_OPENAI_API_KEY}", argv)


if __name__ == "__main__":
    unittest.main()
