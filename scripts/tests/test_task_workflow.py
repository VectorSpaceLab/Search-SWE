"""Offline task contribution, validation, and additive asset publication regressions."""

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
from check_tasks import check_package, discover
from download_assets import destination_path, restore
from prepare_hf_upload import prepare
from task_paths import select_task

SCAFFOLD = SCRIPTS.parent / ".agents/skills/create-searchswe-task/scripts/scaffold_task.py"


class TaskWorkflow(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.repo = self.root / "repo"
        (self.repo / "tasks").mkdir(parents=True)
        (self.repo / "docker").mkdir()
        (self.repo / "docker/README.md").write_text("fixture")
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.name", "Maintainer")
        self.git("config", "user.email", "maintainer@example.test")
        (self.repo / ".gitignore").write_text("__pycache__/\n/jobs/\n")
        shutil.copytree(SCRIPTS, self.repo / "scripts", ignore=shutil.ignore_patterns("tests", "__pycache__"))
        shutil.copytree(SCRIPTS.parent / ".agents/skills/maintain-searchswe-task",
                        self.repo / ".agents/skills/maintain-searchswe-task",
                        ignore=shutil.ignore_patterns("__pycache__", "test_*.py"))
        self.git("add", ".")
        self.git("commit", "-qm", "base")
        self.base = self.git("rev-parse", "HEAD").strip()
        self.source = "tasks/example-search"
        self.task = self.repo / self.source
        result = self.scaffold("Alice")
        self.assertEqual(result.returncode, 0, result.stderr)
        readme = self.task / "README.md"
        readme.write_text(readme.read_text() + f"\nPackage: {self.source}\n")

    def git(self, *args, **kwargs):
        return subprocess.run(["git", *args], cwd=self.repo, check=True,
                              capture_output=True, text=True, **kwargs).stdout

    def scaffold(self, name, task_name="example-search"):
        return subprocess.run([sys.executable, str(SCAFFOLD), task_name, "--repo-root", str(self.repo),
                               "--author", f"{name} Example"], capture_output=True, text=True)

    def cli(self, script, *args):
        env = {k: v for k, v in os.environ.items() if not k.startswith(("AGENT_", "CONTAINER_", "VERIFIER_"))}
        return subprocess.run([sys.executable, str(self.repo / "scripts" / script), *args],
                              cwd=self.root, env=env, capture_output=True, text=True)

    def asset(self, task=None):
        task = task or self.task
        if task != self.task:
            (task / "task.toml").write_text((task / "task.toml").read_text().replace("example-search", task.name))
        content = b"fixture corpus\n"
        entry = {"path": "data/corpus.txt", "size_bytes": len(content),
                 "sha256": hashlib.sha256(content).hexdigest(),
                 "source": {"repo_id": "search-swe/Search-SWE", "repo_type": "dataset", "revision": "a" * 40,
                            "filename": f"tasks/{'example-search' if task == self.task else task.name}/corpus.txt"}}
        (task / "assets.json").write_text(json.dumps({"schema_version": 1, "files": [entry]}))
        data = self.root / "new-data"
        path = data / entry["source"]["filename"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return entry, data

    def commit_task(self):
        self.git("checkout", "-qb", "contribution")
        self.git("add", ".")
        self.git("commit", "-qm", "Alice writes task", "--author", "Alice Example <alice@example.test>")

    def test_flat_names_collisions_and_path_boundaries(self):
        for name in ("hybrid-search", "vector-search"):
            self.assertEqual(self.scaffold("Alice", name).returncode, 0)
            self.assertTrue((self.repo / "tasks" / name / "task.toml").is_file())
        self.assertNotEqual(self.scaffold("Bob").returncode, 0)
        self.assertEqual(self.scaffold("Bob", "other-search").returncode, 0)
        current = self.cli("check_tasks.py")
        self.assertEqual(current.returncode, 0, current.stdout + current.stderr)
        for name in ("../escape", "/absolute", "Élodie", "123", "all", "task-1-1", "one-two-three-four-five-six"):
            self.assertNotEqual(self.scaffold("Alice", name).returncode, 0)
        for name in ("../repo/" + self.source, "/" + self.source, self.source + "/../example-search",
                     "tasks/alice/example-search"):
            with self.assertRaises(ValueError):
                select_task(self.repo, name)
        (self.task / "escape").symlink_to(self.root)
        with self.assertRaises(ValueError):
            select_task(self.repo, self.source)

    def test_symlink_roots_and_download_parent_rejected(self):
        shutil.rmtree(self.repo / "tasks")
        (self.repo / "tasks").symlink_to(self.root)
        self.assertNotEqual(self.scaffold("Alice").returncode, 0)
        with self.assertRaises(ValueError):
            discover(self.repo)
        link = self.root / "linked"
        link.symlink_to(self.repo)
        with self.assertRaises(ValueError):
            destination_path(link / "output", Path("data/file"))

    def test_validator_reuses_release_checks_and_static_parsing(self):
        self.assertEqual(check_package(self.repo, self.task), [])
        self.asset()
        self.assertEqual(check_package(self.repo, self.task), [])
        manifest = json.loads((self.task / "assets.json").read_text())
        manifest["files"][0]["source"]["revision"] = "main"
        (self.task / "assets.json").write_text(json.dumps(manifest))
        self.assertTrue(any("immutable" in e for e in check_package(self.repo, self.task)))
        (self.task / "tests/broken.py").write_text("def broken(\n")
        self.assertTrue(check_package(self.repo, self.task))

    def test_static_validator_does_not_execute_task_code(self):
        sentinel = self.root / "must-not-exist"
        (self.task / "tests/untrusted.py").write_text(
            f"from pathlib import Path\nPath({str(sentinel)!r}).touch()\n")
        (self.task / "tests/untrusted.sh").write_text(f"#!/bin/bash\ntouch {sentinel}\n")
        self.assertEqual(check_package(self.repo, self.task), [])
        self.assertFalse(sentinel.exists())

    def test_task_rejects_type_metadata_and_name_mismatch(self):
        config = self.task / "task.toml"
        original = config.read_text()
        config.write_text(original.replace("[metadata]", '[metadata]\ntask_type = "create"'))
        self.assertTrue(any("unsupported metadata field: task_type" in error for error in check_package(self.repo, self.task)))
        config.write_text(original)
        config.write_text(original.replace("search-swe/example-search", "search-swe/different-search"))
        self.assertTrue(any("Expected task name" in error for error in check_package(self.repo, self.task)))

    def test_validator_scans_payload_secret_forced_asset_author_id_and_ignore_rules(self):
        entry, _ = self.asset()
        local = self.task / entry["path"]
        local.parent.mkdir()
        local.write_text("fixture corpus\n")
        self.git("add", "-f", str(local.relative_to(self.repo)))
        errors = check_package(self.repo, self.task)
        self.assertTrue(any("runtime asset would enter Git" in e for e in errors))
        self.git("reset", "-q")
        (self.task / ".gitignore").write_text("")
        errors = check_package(self.repo, self.task)
        self.assertTrue(any("not ignored" in e for e in errors))
        (self.task / "leak.txt").write_text("hf_" + "a" * 30)
        (self.task / "task.toml").write_text((self.task / "task.toml").read_text().replace("Alice Example", "Search-SWE"))
        errors = check_package(self.repo, self.task)
        for expected in ("credential", "authors"):
            self.assertTrue(any(expected in e for e in errors), errors)

    def test_discovery_incomplete_and_review_versus_merge_ready(self):
        self.assertEqual(discover(self.repo), [self.task])
        result = self.cli("check_tasks.py")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Review-stage task static check", result.stdout)
        self.assertEqual(self.cli("check_tasks.py", "--merge-ready").returncode, 0)
        incomplete = self.repo / "tasks/incomplete-search"
        incomplete.mkdir(parents=True)
        self.assertIn(incomplete, discover(self.repo))
        self.assertNotEqual(self.cli("check_tasks.py").returncode, 0)

    def test_discovery_downloads_and_launches_tasks_by_name(self):
        self.asset()
        result = self.cli("download_assets.py", "--task", "all", "--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Selected 1 files", result.stdout)
        result = self.cli("download_assets.py", "--task-path", self.source, "--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("example-search/data/corpus.txt", result.stdout)
        for name in ("example-search", "other-search"):
            if name != "example-search":
                self.scaffold("Bob", name)
            result = self.cli("run_task.py", "--task", name,
                              "--agent", "pi", "--model", "deepseek/deepseek-flash", "--dry-run")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(f"jobs/{name}", result.stdout)

    def test_task_launch_reaches_mock_harbor(self):
        binary = self.root / "bin"
        binary.mkdir()
        harbor = binary / "harbor"
        harbor.write_text(f"#!{sys.executable}\nimport json, sys\nprint(json.dumps(sys.argv[1:]))\n")
        harbor.chmod(0o755)
        with patch.dict(os.environ, {"PATH": str(binary) + os.pathsep + os.environ.get("PATH", ""),
                                     "DEEPSEEK_API_KEY": "fixture-only"}):
            result = self.cli("run_task.py", "--task-path", self.source, "--agent", "pi",
                              "--model", "deepseek/deepseek-flash")
        self.assertEqual(result.returncode, 0, result.stderr)
        command = json.loads(result.stdout.splitlines()[-1])
        self.assertEqual(command[command.index("--path") + 1], str(self.task))
        self.assertEqual(command[command.index("-o") + 1], str(self.repo / "jobs" / self.task.name))
        self.assertNotIn("fixture-only", result.stdout)

    def test_offline_download_into_task_and_alternate_output(self):
        entry, data = self.asset()
        result = self.cli("download_assets.py", "--task-path", self.source, "--local-data-dir", str(data))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.task / entry["path"]).is_file())
        output = self.root / "alternate"
        result = self.cli("download_assets.py", "--task-path", self.source, "--local-data-dir", str(data),
                          "--output-dir", str(output))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((output / self.task.name / entry["path"]).is_file())
        self.assertEqual(self.cli("download_assets.py", "--task-path", self.source, "--verify-only").returncode, 0)

    def test_personal_pinned_dataset_download_is_mocked_and_verified(self):
        entry, data = self.asset()
        source_file = data / entry["source"]["filename"]
        entry["source"]["repo_id"] = "alice/development"
        args = SimpleNamespace(cache_dir=None, local_files_only=True, force=False, verify_only=False)
        with patch("huggingface_hub.hf_hub_download", return_value=str(source_file)) as download:
            self.assertEqual(restore(self.task, self.task, entry, {}, args), "downloaded")
        self.assertEqual(download.call_args.kwargs["repo_id"], "alice/development")
        self.assertEqual(download.call_args.kwargs["revision"], "a" * 40)
        self.assertTrue(download.call_args.kwargs["local_files_only"])
        (self.task / entry["path"]).unlink()
        entry["source"]["revision"] = "main"
        with patch("huggingface_hub.hf_hub_download") as download:
            with self.assertRaises(ValueError):
                restore(self.task, self.task, entry, {}, args)
            download.assert_not_called()

    def test_direct_contribution_preserves_authors_and_merge_history(self):
        self.asset()
        self.commit_task()
        for name, author in (("hybrid-search", "Alice"), ("vector-search", "Bob")):
            self.assertEqual(self.scaffold(author, name).returncode, 0)
            self.asset(self.repo / "tasks" / name)
            self.git("add", ".")
            self.git("commit", "-qm", f"Add {name}", "--author", f"{author} Example <{author.lower()}@example.test>")
        result = self.cli("check_tasks.py", "--merge-ready", "--base", self.base)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.git("checkout", "-q", "main")
        self.git("merge", "--no-ff", "-qm", "Merge task PR", "contribution")
        self.assertEqual(len(self.git("rev-list", "--parents", "-n", "1", "HEAD").split()), 3)
        for name, author in (("example-search", "Alice"), ("vector-search", "Bob")):
            self.assertIn(f"author {author} Example", self.git("blame", "--line-porcelain", f"tasks/{name}/instruction.md"))
        self.assertEqual(self.cli("check_release.py").returncode, 0)

    def test_merge_ready_checks_official_sources_namespace_and_revision(self):
        entry, _ = self.asset()
        for field, value, message in (("repo_id", "alice/development", "search-swe/Search-SWE"),
                                      ("filename", "tasks/other-search/corpus.txt", "tasks/example-search/"),
                                      ("revision", "main", "immutable")):
            with self.subTest(field=field):
                manifest = {"schema_version": 1, "files": [entry]}
                original = entry["source"][field]
                entry["source"][field] = value
                (self.task / "assets.json").write_text(json.dumps(manifest))
                if field == "repo_id":
                    result = self.cli("check_tasks.py")
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                result = self.cli("check_tasks.py", "--merge-ready")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(message, result.stdout)
                entry["source"][field] = original
        (self.task / "assets.json").write_text(json.dumps({"schema_version": 1, "files": [entry]}))
        self.assertEqual(self.cli("check_tasks.py", "--merge-ready").returncode, 0)

    def test_all_tasks_receive_syntax_checks_and_new_tasks_require_authors(self):
        config = self.task / "task.toml"
        original = config.read_text()
        config.write_text(original.replace("Alice Example", "Search-SWE"))
        for args in ((), (self.source,)):
            self.assertNotEqual(self.cli("check_tasks.py", *args).returncode, 0)
        config.write_text(original)
        self.commit_task()
        broken = self.task / "tests/broken.py"
        broken.write_text("def broken(\n")
        for args in ((), ("--merge-ready",)):
            self.assertNotEqual(self.cli("check_tasks.py", *args).returncode, 0)
        broken.unlink()
        config = self.task / "task.toml"
        config.write_text(config.read_text().replace("Alice Example", "Search-SWE"))
        self.assertNotEqual(self.cli("check_tasks.py", "--base", self.base).returncode, 0)
        self.assertNotEqual(self.cli("check_tasks.py", "--base", "main").returncode, 0)

    def test_existing_task_authors_survive_edits_and_renames(self):
        config = self.task / "task.toml"
        config.write_text(config.read_text().replace("Alice Example", "Search-SWE"))
        self.commit_task()
        base = self.git("rev-parse", "HEAD").strip()
        self.assertEqual(self.cli("check_tasks.py", self.source).returncode, 0)
        (self.task / "README.md").write_text("Updated task documentation\n")
        self.git("add", ".")
        self.git("commit", "-qm", "Document task")
        self.assertEqual(self.cli("check_tasks.py", "--base", base).returncode, 0)
        self.git("mv", self.source, "tasks/renamed-search")
        config = self.repo / "tasks/renamed-search/task.toml"
        config.write_text(config.read_text().replace("example-search", "renamed-search"))
        self.git("add", ".")
        self.git("commit", "-qm", "Rename task")
        result = self.cli("check_tasks.py", "--merge-ready", "--base", base)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_nested_task_directories_fail_validation(self):
        nested = self.repo / "tasks/alice/nested-search"
        shutil.copytree(self.task, nested)
        self.assertIn(nested, discover(self.repo))
        result = self.cli("check_tasks.py")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("tasks/<task-name>", result.stdout)

    def test_incremental_manifest_preserves_old_entries_without_old_data(self):
        target = self.repo / "tasks/example-search"
        entry, data = self.asset(target)
        old = {"path": "tasks/reasoning-query-rewriting/old.bin", "size_bytes": 500, "sha256": "b" * 64, "license": "fixture"}
        snapshot = self.root / "official.json"
        snapshot.write_text(json.dumps({"schema_version": 1, "files": [old], "extra": "preserve"}))
        output = self.root / "upload"
        self.assertEqual(prepare(snapshot, target, data, output), 1)
        merged = json.loads((output / "manifest.json").read_text())
        self.assertEqual(merged["files"][0], old)
        self.assertEqual(merged["extra"], "preserve")
        self.assertFalse((output / old["path"]).exists())
        self.assertTrue((output / entry["source"]["filename"]).is_file())
        with self.assertRaises(ValueError):
            prepare(snapshot, target, data, output)
        # Existing official paths are never replaced, even if bytes match.
        snapshot.write_text(json.dumps(merged))
        with self.assertRaises(ValueError):
            prepare(snapshot, target, data, self.root / "collision")
        snapshot.write_text(json.dumps({"schema_version": 1, "files": [old]}))
        (data / entry["source"]["filename"]).write_text("corrupt")
        with self.assertRaises(ValueError):
            prepare(snapshot, target, data, self.root / "corrupt")
        self.assertFalse((self.root / "corrupt").exists())

    def test_incremental_rejects_traversal_and_symlinks(self):
        target = self.repo / "tasks/example-search"
        entry, data = self.asset(target)
        snapshot = self.root / "official.json"
        snapshot.write_text(json.dumps({"schema_version": 1, "files": [
            {"path": "../escape", "size_bytes": 1, "sha256": "a" * 64}]}))
        with self.assertRaises(ValueError):
            prepare(snapshot, target, data, self.root / "upload")
        snapshot.write_text(json.dumps({"schema_version": 1, "files": []}))
        (data / "link").symlink_to(self.root)
        with self.assertRaises(ValueError):
            prepare(snapshot, target, data, self.root / "upload")


if __name__ == "__main__":
    unittest.main()
