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
        self.source = "task-submissions/alice/1-x-1"
        self.task = self.repo / self.source
        result = self.scaffold("Alice")
        self.assertEqual(result.returncode, 0, result.stderr)

    def git(self, *args, **kwargs):
        return subprocess.run(["git", *args], cwd=self.repo, check=True,
                              capture_output=True, text=True, **kwargs).stdout

    def scaffold(self, name, task_id="task-1-x-1"):
        mode = "optimization" if task_id.startswith("task-2-") else "implementation"
        return subprocess.run([sys.executable, str(SCAFFOLD), task_id, "--repo-root", str(self.repo),
                               "--submission-first-name", name, "--author", f"{name} Example",
                               "--mode", mode], capture_output=True, text=True)

    def cli(self, script, *args):
        env = {k: v for k, v in os.environ.items() if not k.startswith(("AGENT_", "CONTAINER_", "VERIFIER_"))}
        return subprocess.run([sys.executable, str(self.repo / "scripts" / script), *args],
                              cwd=self.root, env=env, capture_output=True, text=True)

    def asset(self, task=None):
        task = task or self.task
        if task != self.task:
            (task / "task.toml").write_text((task / "task.toml").read_text().replace("task-1-x-1", task.name))
        content = b"fixture corpus\n"
        entry = {"path": "data/corpus.txt", "size_bytes": len(content),
                 "sha256": hashlib.sha256(content).hexdigest(),
                 "source": {"repo_id": "search-swe/Search-SWE", "repo_type": "dataset", "revision": "a" * 40,
                            "filename": f"tasks/{'task-1-x-1' if task == self.task else task.name}/corpus.txt"}}
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

    def test_namespace_reuse_explicit_name_suffix_and_path_boundaries(self):
        self.assertEqual(self.scaffold("Alice", "task-1-x-2").returncode, 0)
        self.assertEqual(self.scaffold("Alice", "task-2-x-1").returncode, 0)
        self.assertTrue((self.repo / "task-submissions/alice/1-x-2/task.toml").is_file())
        self.assertTrue((self.repo / "task-submissions/alice/2-x-1/task.toml").is_file())
        self.assertEqual(self.scaffold("Alice-2").returncode, 0)
        self.assertTrue((self.repo / "task-submissions/alice-2/1-x-1/task.toml").is_file())
        current = self.cli("check_submission.py")
        self.assertNotEqual(current.returncode, 0)
        self.assertIn("exactly one contributor namespace", current.stdout)
        for name in ("../alice", "/absolute", "Élodie", "123"):
            self.assertNotEqual(self.scaffold(name).returncode, 0)
        for name in ("../repo/" + self.source, "/" + self.source, self.source + "/../1-x-1"):
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

    def test_submission_rejects_category_mode_mismatch(self):
        config = self.task / "task.toml"
        config.write_text(config.read_text().replace('task_type = "create"', 'task_type = "optimize"'))
        self.assertTrue(any("Category 1 requires" in error for error in check_submission(self.repo, self.task)))

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
        for expected in ("credential", "authors", "unexpected task IDs"):
            self.assertTrue(any(expected in e for e in errors), errors)

    def test_discovery_incomplete_and_review_versus_merge_ready(self):
        self.assertEqual(discover(self.repo), [self.task])
        result = self.cli("check_submission.py")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("NOT mean merge-ready", result.stdout)
        self.assertNotEqual(self.cli("check_submission.py", "--merge-ready").returncode, 0)
        incomplete = self.repo / "task-submissions/bob/2-x-1"
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
        self.assertIn("task-submissions/alice/1-x-1/data/corpus.txt", result.stdout)
        for name in ("alice", "alice-2"):
            if name != "alice":
                self.scaffold("Alice-2")
            result = self.cli("run_task.py", "--task-path", f"task-submissions/{name}/1-x-1",
                              "--agent", "pi", "--model", "deepseek/deepseek-flash", "--dry-run")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(f"jobs/task-submissions/{name}/1-x-1", result.stdout)
        self.assertNotEqual(self.cli("run_task.py", "--task", "task-1-x-1", "--dry-run").returncode, 0)

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
        promote(self.repo, self.source, "task-1-6", "rename", dry_run=True)
        self.assertTrue(self.task.exists())
        self.assertFalse(self.git("status", "--porcelain"))
        promote(self.repo, self.source, "task-1-6", "rename")
        with self.assertRaises(ValueError):
            promote(self.repo, self.source, "task-1-6", "finalize")
        self.git("commit", "-qm", "Pure rename by maintainer")
        target = self.repo / "tasks/task-1-6"
        promote(self.repo, self.source, "task-1-6", "finalize", dry_run=True)
        self.assertIn("task-1-x-1", (target / "task.toml").read_text())
        promote(self.repo, self.source, "task-1-6", "finalize")
        self.git("add", ".")
        self.git("commit", "-qm", "Finalize by maintainer")
        self.git("checkout", "-q", "main")
        self.git("merge", "--no-ff", "-qm", "Merge task PR", "contribution")
        self.assertEqual(len(self.git("rev-list", "--parents", "-n", "1", "HEAD").split()), 3)
        history = self.git("log", "--follow", "--format=%an %s", "--", "tasks/task-1-6/instruction.md")
        self.assertIn("Alice Example Alice writes task", history)
        blame = self.git("blame", "--line-porcelain", "tasks/task-1-6/instruction.md")
        self.assertIn("author Alice Example", blame)
        self.assertIn("author Maintainer", blame)
        self.assertFalse(list((self.repo / "task-submissions").rglob("task.toml")))
        self.assertEqual(self.cli("check_submission.py", "--merge-ready").returncode, 0)
        self.assertEqual(self.cli("check_release.py").returncode, 0)

    def test_promotion_refuses_collision_category_traversal_and_nonpure_commit(self):
        self.commit_submission()
        for source, target in ((self.source, "task-2-6"), (self.source, "../task-1-6"),
                               ("../" + self.source, "task-1-6")):
            with self.assertRaises(ValueError):
                promote(self.repo, source, target, "rename")
        collision = self.repo / "tasks/task-1-6"
        collision.mkdir()
        with self.assertRaises(ValueError):
            promote(self.repo, self.source, "task-1-6", "rename")
        collision.rmdir()
        promote(self.repo, self.source, "task-1-6", "rename")
        (self.repo / "docker/README.md").write_text("unrelated edit")
        self.git("add", ".")
        self.git("commit", "-qm", "Not a pure rename")
        with self.assertRaises(ValueError):
            promote(self.repo, self.source, "task-1-6", "finalize")

    def test_merge_ready_rechecks_promoted_syntax_paths_and_new_authors(self):
        self.commit_submission()
        promote(self.repo, self.source, "task-1-6", "rename")
        self.git("commit", "-qm", "Pure rename")
        promote(self.repo, self.source, "task-1-6", "finalize")
        target = self.repo / "tasks/task-1-6"
        self.git("add", ".")
        self.git("commit", "-qm", "Finalize")
        self.assertEqual(self.cli("check_submission.py", "--merge-ready").returncode, 0)
        readme = target / "README.md"
        original = readme.read_text()
        readme.write_text(original + "\ntask-submissions/alice/1-x-1\n")
        self.assertNotEqual(self.cli("check_submission.py", "--merge-ready").returncode, 0)
        readme.write_text(original)
        broken = target / "tests/broken.py"
        broken.write_text("def broken(\n")
        self.assertNotEqual(self.cli("check_submission.py", "--merge-ready").returncode, 0)
        broken.unlink()
        config = target / "task.toml"
        config.write_text(config.read_text().replace("Alice Example", "Search-SWE"))
        self.assertNotEqual(self.cli("check_submission.py", "--base", self.base).returncode, 0)

    def test_base_allows_multiple_tasks_in_one_namespace_and_rejects_two(self):
        self.scaffold("Alice", "task-1-x-2")
        self.scaffold("Alice", "task-2-x-1")
        self.git("add", ".")
        self.git("commit", "-qm", "three Alice submissions")
        result = self.cli("check_submission.py", "--base", self.base)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.scaffold("Bob")
        self.git("add", ".")
        self.git("commit", "-qm", "Bob submission")
        result = self.cli("check_submission.py", "--base", self.base)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("exactly one contributor namespace", result.stdout)

    def test_base_rejects_direct_formal_task_without_submission_history(self):
        shutil.rmtree(self.repo / "task-submissions")
        result = subprocess.run(
            [sys.executable, str(SCAFFOLD), "task-1-6", "--repo-root", str(self.repo),
             "--author", "Alice Example"], capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.git("add", ".")
        self.git("commit", "-qm", "Bypass submission buffer")
        result = self.cli("check_submission.py", "--merge-ready", "--base", self.base)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("require exactly one contributor submission namespace", result.stdout)

    def test_base_rejects_temporary_ordinal_reuse_after_promotion(self):
        self.git("add", ".")
        self.git("commit", "-qm", "First use of ordinal")
        for target_id in ("task-1-6", "task-1-7"):
            promote(self.repo, self.source, target_id, "rename")
            self.git("commit", "-qm", f"Pure rename {target_id}")
            promote(self.repo, self.source, target_id, "finalize")
            self.git("add", ".")
            self.git("commit", "-qm", f"Finalize {target_id}")
            if target_id == "task-1-6":
                result = self.scaffold("Alice")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.git("add", ".")
                self.git("commit", "-qm", "Reuse ordinal for another task")
        result = self.cli("check_submission.py", "--merge-ready", "--base", self.base)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Temporary task ordinals must not be reused", result.stdout)

    def test_multiple_tasks_promote_independently_and_history_keeps_namespace(self):
        self.scaffold("Alice", "task-2-x-1")
        self.git("checkout", "-qb", "multi-promotion")
        self.git("add", ".")
        self.git("commit", "-qm", "Alice submits two tasks", "--author", "Alice Example <alice@example.test>")
        for source, target_id in ((self.source, "task-1-6"),
                                  ("task-submissions/alice/2-x-1", "task-2-6")):
            promote(self.repo, source, target_id, "rename")
            self.git("commit", "-qm", f"Pure rename {target_id}")
            promote(self.repo, source, target_id, "finalize")
            self.git("add", ".")
            self.git("commit", "-qm", f"Finalize {target_id}")
        self.assertEqual(self.cli("check_submission.py", "--merge-ready", "--base", self.base).returncode, 0)
        self.assertIn("Alice Example", self.git("log", "--follow", "--format=%an", "--",
                                                "tasks/task-1-6/instruction.md"))
        self.assertIn("Alice Example", self.git("log", "--follow", "--format=%an", "--",
                                                "tasks/task-2-6/instruction.md"))

        self.scaffold("Bob")
        self.git("add", ".")
        self.git("commit", "-qm", "Bob submission", "--author", "Bob Example <bob@example.test>")
        bob_source = "task-submissions/bob/1-x-1"
        promote(self.repo, bob_source, "task-1-7", "rename")
        self.git("commit", "-qm", "Pure rename task-1-7")
        promote(self.repo, bob_source, "task-1-7", "finalize")
        self.git("add", ".")
        self.git("commit", "-qm", "Finalize task-1-7")
        result = self.cli("check_submission.py", "--merge-ready", "--base", self.base)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("exactly one contributor namespace", result.stdout)

    def test_base_history_checks_every_side_of_fully_promoted_merge(self):
        self.git("checkout", "-qb", "alice-history")
        self.git("add", ".")
        self.git("commit", "-qm", "Alice submission")
        promote(self.repo, self.source, "task-1-6", "rename")
        self.git("commit", "-qm", "Pure rename Alice")
        promote(self.repo, self.source, "task-1-6", "finalize")
        self.git("add", ".")
        self.git("commit", "-qm", "Finalize Alice")

        self.git("checkout", "-qb", "bob-history", self.base)
        (self.repo / "tasks").mkdir(exist_ok=True)
        result = self.scaffold("Bob")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.git("add", ".")
        self.git("commit", "-qm", "Bob submission")
        bob_source = "task-submissions/bob/1-x-1"
        promote(self.repo, bob_source, "task-1-7", "rename")
        self.git("commit", "-qm", "Pure rename Bob")
        promote(self.repo, bob_source, "task-1-7", "finalize")
        self.git("add", ".")
        self.git("commit", "-qm", "Finalize Bob")

        self.git("checkout", "alice-history")
        self.git("merge", "--no-ff", "bob-history", "-m", "Merge Bob history")
        result = self.cli("check_submission.py", "--merge-ready", "--base", self.base)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("exactly one contributor namespace", result.stdout)

    def test_base_history_rejects_unsafe_submission_paths(self):
        self.git("checkout", "-qb", "unsafe-history")
        unsafe = self.repo / "task-submissions/not-a-package/file.txt"
        unsafe.parent.mkdir(parents=True)
        unsafe.write_text("unsafe historical path")
        self.git("add", ".")
        self.git("commit", "-qm", "Malformed submission path")
        result = self.cli("check_submission.py", "--base", self.base)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Malformed task submission path", result.stdout)

    def test_incremental_manifest_preserves_old_entries_without_old_data(self):
        target = self.repo / "tasks/task-1-6"
        shutil.copytree(self.task, target)
        entry, data = self.asset(target)
        old = {"path": "tasks/task-1-1/old.bin", "size_bytes": 500, "sha256": "b" * 64, "license": "fixture"}
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
        target = self.repo / "tasks/task-1-6"
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
