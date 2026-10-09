"""Offline submission, promotion/history, and additive asset publication regressions."""

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
from check_submission import check_submission, discover
from download_assets import destination_path, restore
from prepare_hf_upload import prepare
from promote_task import promote
from task_paths import select_task

SCAFFOLD = SCRIPTS.parent / ".agents/skills/create-searchswe-task/scripts/scaffold_task.py"


class SubmissionWorkflow(unittest.TestCase):
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
        self.source = "task-submissions/example-search"
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

    def commit_submission(self):
        self.git("checkout", "-qb", "contribution")
        self.git("add", ".")
        self.git("commit", "-qm", "Alice writes task", "--author", "Alice Example <alice@example.test>")

    def test_flat_names_collisions_and_path_boundaries(self):
        for name in ("hybrid-search", "vector-search"):
            self.assertEqual(self.scaffold("Alice", name).returncode, 0)
            self.assertTrue((self.repo / "task-submissions" / name / "task.toml").is_file())
        self.assertNotEqual(self.scaffold("Bob").returncode, 0)
        self.assertEqual(self.scaffold("Bob", "other-search").returncode, 0)
        current = self.cli("check_submission.py")
        self.assertEqual(current.returncode, 0, current.stdout + current.stderr)
        for name in ("../escape", "/absolute", "Élodie", "123", "all", "task-1-1", "one-two-three-four-five-six"):
            self.assertNotEqual(self.scaffold("Alice", name).returncode, 0)
        for name in ("../repo/" + self.source, "/" + self.source, self.source + "/../example-search",
                     "task-submissions/alice/example-search"):
            with self.assertRaises(ValueError):
                select_task(self.repo, name)
        (self.task / "escape").symlink_to(self.root)
        with self.assertRaises(ValueError):
            select_task(self.repo, self.source)

    def test_symlink_roots_and_download_parent_rejected(self):
        shutil.rmtree(self.repo / "task-submissions")
        (self.repo / "task-submissions").symlink_to(self.root)
        self.assertNotEqual(self.scaffold("Alice").returncode, 0)
        with self.assertRaises(ValueError):
            discover(self.repo)
        link = self.root / "linked"
        link.symlink_to(self.repo)
        with self.assertRaises(ValueError):
            destination_path(link / "output", Path("data/file"))

    def test_validator_reuses_release_checks_and_static_parsing(self):
        self.assertEqual(check_submission(self.repo, self.task), [])
        self.asset()
        self.assertEqual(check_submission(self.repo, self.task), [])
        manifest = json.loads((self.task / "assets.json").read_text())
        manifest["files"][0]["source"]["revision"] = "main"
        (self.task / "assets.json").write_text(json.dumps(manifest))
        self.assertTrue(any("immutable" in e for e in check_submission(self.repo, self.task)))
        (self.task / "tests/broken.py").write_text("def broken(\n")
        self.assertTrue(check_submission(self.repo, self.task))

    def test_static_validator_does_not_execute_task_code(self):
        sentinel = self.root / "must-not-exist"
        (self.task / "tests/untrusted.py").write_text(
            f"from pathlib import Path\nPath({str(sentinel)!r}).touch()\n")
        (self.task / "tests/untrusted.sh").write_text(f"#!/bin/bash\ntouch {sentinel}\n")
        self.assertEqual(check_submission(self.repo, self.task), [])
        self.assertFalse(sentinel.exists())

    def test_submission_rejects_obsolete_type_and_formal_name_collision(self):
        config = self.task / "task.toml"
        original = config.read_text()
        config.write_text(original.replace("[metadata]", '[metadata]\ntask_type = "create"'))
        self.assertTrue(any("remove metadata.task_type" in error for error in check_submission(self.repo, self.task)))
        config.write_text(original)
        shutil.copytree(self.task, self.repo / "tasks/example-search")
        self.assertTrue(any("collides" in error for error in check_submission(self.repo, self.task)))

    def test_validator_scans_payload_secret_forced_asset_author_id_and_ignore_rules(self):
        entry, _ = self.asset()
        local = self.task / entry["path"]
        local.parent.mkdir()
        local.write_text("fixture corpus\n")
        self.git("add", "-f", str(local.relative_to(self.repo)))
        errors = check_submission(self.repo, self.task)
        self.assertTrue(any("runtime asset would enter Git" in e for e in errors))
        self.git("reset", "-q")
        (self.task / ".gitignore").write_text("")
        errors = check_submission(self.repo, self.task)
        self.assertTrue(any("not ignored" in e for e in errors))
        (self.task / "leak.txt").write_text("hf_" + "a" * 30)
        (self.task / "task.toml").write_text((self.task / "task.toml").read_text().replace("Alice Example", "Search-SWE"))
        (self.task / "README.md").write_text("task-1-999\n")
        errors = check_submission(self.repo, self.task)
        for expected in ("credential", "authors", "obsolete numbered task reference"):
            self.assertTrue(any(expected in e for e in errors), errors)

    def test_discovery_incomplete_and_review_versus_merge_ready(self):
        self.assertEqual(discover(self.repo), [self.task])
        result = self.cli("check_submission.py")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("NOT mean merge-ready", result.stdout)
        self.assertNotEqual(self.cli("check_submission.py", "--merge-ready").returncode, 0)
        incomplete = self.repo / "task-submissions/incomplete-search"
        incomplete.mkdir(parents=True)
        self.assertIn(incomplete, discover(self.repo))
        self.assertNotEqual(self.cli("check_submission.py").returncode, 0)

    def test_formal_discovery_excludes_submissions_and_explicit_launch_is_namespaced(self):
        self.asset()
        result = self.cli("download_assets.py", "--task", "all", "--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Selected 0 files", result.stdout)
        result = self.cli("download_assets.py", "--task-path", self.source, "--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("task-submissions/example-search/data/corpus.txt", result.stdout)
        for name in ("example-search", "other-search"):
            if name != "example-search":
                self.scaffold("Bob", name)
            result = self.cli("run_task.py", "--task-path", f"task-submissions/{name}",
                              "--agent", "pi", "--model", "deepseek/deepseek-flash", "--dry-run")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(f"jobs/task-submissions/{name}", result.stdout)
        self.assertNotEqual(self.cli("run_task.py", "--task", "example-search", "--dry-run").returncode, 0)

    def test_submission_launch_reaches_mock_harbor_without_formal_registration(self):
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
        self.assertEqual(command[command.index("-o") + 1], str(self.repo / "jobs" / self.source))
        self.assertNotIn("fixture-only", result.stdout)

    def test_offline_download_into_submission_and_alternate_output(self):
        entry, data = self.asset()
        result = self.cli("download_assets.py", "--task-path", self.source, "--local-data-dir", str(data))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.task / entry["path"]).is_file())
        output = self.root / "alternate"
        result = self.cli("download_assets.py", "--task-path", self.source, "--local-data-dir", str(data),
                          "--output-dir", str(output))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((output / self.source / entry["path"]).is_file())
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

    def test_two_phase_promotion_preserves_follow_blame_and_merge_history(self):
        self.commit_submission()
        promote(self.repo, self.source, "example-search", "rename", dry_run=True)
        self.assertTrue(self.task.exists())
        self.assertFalse(self.git("status", "--porcelain"))
        promote(self.repo, self.source, "example-search", "rename")
        with self.assertRaises(ValueError):
            promote(self.repo, self.source, "example-search", "finalize")
        self.git("commit", "-qm", "Pure rename by maintainer")
        target = self.repo / "tasks/example-search"
        promote(self.repo, self.source, "example-search", "finalize", dry_run=True)
        self.assertIn("example-search", (target / "task.toml").read_text())
        promote(self.repo, self.source, "example-search", "finalize")
        self.git("add", ".")
        self.git("commit", "-qm", "Finalize by maintainer", "--allow-empty")
        self.git("checkout", "-q", "main")
        self.git("merge", "--no-ff", "-qm", "Merge task PR", "contribution")
        self.assertEqual(len(self.git("rev-list", "--parents", "-n", "1", "HEAD").split()), 3)
        history = self.git("log", "--follow", "--format=%an %s", "--", "tasks/example-search/instruction.md")
        self.assertIn("Alice Example Alice writes task", history)
        blame = self.git("blame", "--line-porcelain", "tasks/example-search/instruction.md")
        self.assertIn("author Alice Example", blame)
        self.assertNotIn("author Maintainer", blame)
        self.assertFalse(list((self.repo / "task-submissions").rglob("task.toml")))
        self.assertEqual(self.cli("check_submission.py", "--merge-ready").returncode, 0)
        self.assertEqual(self.cli("check_release.py").returncode, 0)

    def test_promotion_refuses_collision_rename_traversal_and_nonpure_commit(self):
        self.commit_submission()
        for source, target in ((self.source, "vector-search"), (self.source, "../example-search"),
                               ("../" + self.source, "example-search")):
            with self.assertRaises(ValueError):
                promote(self.repo, source, target, "rename")
        collision = self.repo / "tasks/example-search"
        collision.mkdir()
        with self.assertRaises(ValueError):
            promote(self.repo, self.source, "example-search", "rename")
        collision.rmdir()
        promote(self.repo, self.source, "example-search", "rename")
        (self.repo / "docker/README.md").write_text("unrelated edit")
        self.git("add", ".")
        self.git("commit", "-qm", "Not a pure rename")
        with self.assertRaises(ValueError):
            promote(self.repo, self.source, "example-search", "finalize")

    def test_merge_ready_rechecks_promoted_syntax_paths_and_new_authors(self):
        self.commit_submission()
        promote(self.repo, self.source, "example-search", "rename")
        self.git("commit", "-qm", "Pure rename")
        promote(self.repo, self.source, "example-search", "finalize")
        target = self.repo / "tasks/example-search"
        self.git("add", ".")
        self.git("commit", "-qm", "Finalize", "--allow-empty")
        self.assertEqual(self.cli("check_submission.py", "--merge-ready").returncode, 0)
        readme = target / "README.md"
        original = readme.read_text()
        readme.write_text(original + "\ntask-submissions/example-search\n")
        self.assertNotEqual(self.cli("check_submission.py", "--merge-ready").returncode, 0)
        readme.write_text(original)
        broken = target / "tests/broken.py"
        broken.write_text("def broken(\n")
        self.assertNotEqual(self.cli("check_submission.py", "--merge-ready").returncode, 0)
        broken.unlink()
        config = target / "task.toml"
        config.write_text(config.read_text().replace("Alice Example", "Search-SWE"))
        self.assertNotEqual(self.cli("check_submission.py", "--base", self.base).returncode, 0)

    def test_base_allows_multiple_tasks_and_authors(self):
        self.scaffold("Alice", "hybrid-search")
        self.scaffold("Bob", "vector-search")
        self.git("add", ".")
        self.git("commit", "-qm", "Multiple submissions")
        result = self.cli("check_submission.py", "--base", self.base)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_base_rejects_direct_formal_task_without_submission_history(self):
        shutil.rmtree(self.repo / "task-submissions")
        result = subprocess.run(
            [sys.executable, str(SCAFFOLD), "example-search", "--repo-root", str(self.repo),
             "--author", "Alice Example", "--formal"], capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.git("add", ".")
        self.git("commit", "-qm", "Bypass submission buffer")
        result = self.cli("check_submission.py", "--merge-ready", "--base", self.base)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("require same-PR pure promotion", result.stdout)

    def test_base_rejects_submission_path_reuse(self):
        self.git("add", ".")
        self.git("commit", "-qm", "First submission")
        self.git("rm", "-r", self.source)
        self.git("commit", "-qm", "Remove submission")
        self.assertEqual(self.scaffold("Bob").returncode, 0)
        self.git("add", ".")
        self.git("commit", "-qm", "Reuse submission path")
        result = self.cli("check_submission.py", "--base", self.base)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Submission paths must not be reused", result.stdout)

    def test_multiple_tasks_promote_independently_with_multiple_authors(self):
        self.scaffold("Alice", "vector-search")
        self.git("checkout", "-qb", "multi-promotion")
        self.git("add", ".")
        self.git("commit", "-qm", "Alice submits two tasks", "--author", "Alice Example <alice@example.test>")
        for source, target_id in ((self.source, "example-search"),
                                  ("task-submissions/vector-search", "vector-search")):
            promote(self.repo, source, target_id, "rename")
            self.git("commit", "-qm", f"Pure rename {target_id}")
            promote(self.repo, source, target_id, "finalize")
            self.git("add", ".")
            self.git("commit", "-qm", f"Finalize {target_id}", "--allow-empty")
        self.assertEqual(self.cli("check_submission.py", "--merge-ready", "--base", self.base).returncode, 0)
        self.assertIn("Alice Example", self.git("log", "--follow", "--format=%an", "--",
                                                "tasks/example-search/instruction.md"))
        self.assertIn("Alice Example", self.git("log", "--follow", "--format=%an", "--",
                                                "tasks/vector-search/instruction.md"))

        self.scaffold("Bob", "other-search")
        self.git("add", ".")
        self.git("commit", "-qm", "Bob submission", "--author", "Bob Example <bob@example.test>")
        bob_source = "task-submissions/other-search"
        promote(self.repo, bob_source, "other-search", "rename")
        self.git("commit", "-qm", "Pure rename other-search")
        promote(self.repo, bob_source, "other-search", "finalize")
        self.git("add", ".")
        self.git("commit", "-qm", "Finalize other-search", "--allow-empty")
        result = self.cli("check_submission.py", "--merge-ready", "--base", self.base)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_base_history_checks_every_side_of_fully_promoted_merge(self):
        self.git("checkout", "-qb", "alice-history")
        self.git("add", ".")
        self.git("commit", "-qm", "Alice submission")
        promote(self.repo, self.source, "example-search", "rename")
        self.git("commit", "-qm", "Pure rename Alice")
        promote(self.repo, self.source, "example-search", "finalize")
        self.git("add", ".")
        self.git("commit", "-qm", "Finalize Alice", "--allow-empty")

        self.git("checkout", "-qb", "bob-history", self.base)
        (self.repo / "tasks").mkdir(exist_ok=True)
        result = self.scaffold("Bob", "other-search")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.git("add", ".")
        self.git("commit", "-qm", "Bob submission")
        bob_source = "task-submissions/other-search"
        promote(self.repo, bob_source, "other-search", "rename")
        self.git("commit", "-qm", "Pure rename Bob")
        promote(self.repo, bob_source, "other-search", "finalize")
        self.git("add", ".")
        self.git("commit", "-qm", "Finalize Bob", "--allow-empty")

        self.git("checkout", "alice-history")
        self.git("merge", "--no-ff", "bob-history", "-m", "Merge Bob history")
        result = self.cli("check_submission.py", "--merge-ready", "--base", self.base)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_base_history_rejects_unsafe_submission_paths(self):
        self.git("checkout", "-qb", "unsafe-history")
        unsafe = self.repo / "task-submissions/alice/nested-search/task.toml"
        unsafe.parent.mkdir(parents=True)
        unsafe.write_text("unsafe historical path")
        self.git("add", ".")
        self.git("commit", "-qm", "Malformed submission path")
        result = self.cli("check_submission.py", "--base", self.base)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Malformed task submission path", result.stdout)

    def test_base_recognizes_existing_formal_rename_without_changing_legacy_authors(self):
        # A repository-wide name migration is an edit to an existing package.
        legacy = self.repo / "tasks/task-1-1"
        self.task.rename(legacy)
        readme = legacy / "README.md"
        readme.write_text("Existing formal task\n")
        config = legacy / "task.toml"
        config.write_text(config.read_text().replace("example-search", "task-1-1")
                          .replace("Alice Example", "Search-SWE"))
        self.git("add", ".")
        self.git("commit", "-qm", "Existing legacy formal task")
        base = self.git("rev-parse", "HEAD").strip()
        self.git("mv", "tasks/task-1-1", "tasks/example-search")
        config = self.repo / "tasks/example-search/task.toml"
        config.write_text(config.read_text().replace("task-1-1", "example-search"))
        self.git("add", ".")
        self.git("commit", "-qm", "Rename existing formal task")
        result = self.cli("check_submission.py", "--merge-ready", "--base", base)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_history_rejects_deleted_nested_submission(self):
        unsafe = self.repo / "task-submissions/alice/nested-search/task.toml"
        unsafe.parent.mkdir(parents=True)
        unsafe.write_text("invalid old nested layout")
        self.git("add", ".")
        self.git("commit", "-qm", "Nested submission")
        shutil.rmtree(unsafe.parent.parent)
        self.git("add", "-u")
        self.git("commit", "-qm", "Remove nested submission")
        result = self.cli("check_submission.py", "--base", self.base)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Malformed task submission path", result.stdout)

    def test_history_rejects_renamed_or_nonpure_submission_promotion(self):
        self.commit_submission()
        self.git("mv", self.source, "tasks/other-search")
        target = self.repo / "tasks/other-search"
        for name in ("README.md", "task.toml", "instruction.md"):
            path = target / name
            path.write_text(path.read_text().replace(self.source, "tasks/other-search")
                            .replace("example-search", "other-search"))
        self.git("add", ".")
        self.git("commit", "-qm", "Rename and modify submission")
        result = self.cli("check_submission.py", "--merge-ready", "--base", self.base)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("require same-PR pure promotion", result.stdout)

    def test_official_staging_requires_promotion_even_when_name_is_final(self):
        _, data = self.asset()
        snapshot = self.root / "official.json"
        snapshot.write_text(json.dumps({"schema_version": 1, "files": []}))
        output = self.root / "premature-upload"
        with self.assertRaisesRegex(ValueError, "Promote to tasks/<task-name>"):
            prepare(snapshot, self.task, data, output)
        self.assertFalse(output.exists())

    def test_incremental_manifest_preserves_old_entries_without_old_data(self):
        target = self.repo / "tasks/example-search"
        shutil.copytree(self.task, target)
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
        shutil.copytree(self.task, target)
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
