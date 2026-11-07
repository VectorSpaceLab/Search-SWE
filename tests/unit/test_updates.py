"""Checkout updates against local Git remotes, without network or model APIs."""

from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from search_swe import __version__, repository, updates
from search_swe.cli import main


class UpdateTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.enterContext(patch.dict(os.environ, {
            "GIT_AUTHOR_NAME": "Fixture", "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
            "GIT_COMMITTER_NAME": "Fixture", "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
        }))
        self.root = Path(temporary.name)
        self.source = self.root / "upstream"
        self.source.mkdir()
        self.git(self.source, "init", "-q", "-b", "main")
        (self.source / "pyproject.toml").write_text('[project]\nname="search-swe"\nversion="0.3.0"\n')
        (self.source / "scripts/evaluation").mkdir(parents=True)
        (self.source / "scripts/evaluation/run_task.py").write_text("# fixture\n")
        (self.source / ".gitignore").write_text(".env\ntasks/*/data/\njobs/\n")
        self.task(self.source, "first-search")
        self.commit(self.source)
        self.checkout = self.root / "checkout with spaces"
        subprocess.run(["git", "clone", "--quiet", "--depth", "1", "--single-branch",
                        self.source.as_uri(), str(self.checkout)], check=True, capture_output=True)

    def git(self, root, *args):
        result = subprocess.run(["git", "-c", "core.hooksPath=/dev/null", "-C", str(root), *args],
                                check=True, capture_output=True, text=True)
        return result.stdout.strip()

    def commit(self, root):
        self.git(root, "add", "-A")
        self.git(root, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                 "-c", "commit.gpgsign=false", "commit", "-qm", "Fixture")

    def task(self, root, name):
        path = root / "tasks" / name
        path.mkdir(parents=True)
        (path / "task.toml").write_text('[environment]\ncpus=1\nmemory_mb=1024\n')
        (path / "assets.json").write_text('{"files": []}')

    def advance(self, version="0.3.1"):
        (self.source / "pyproject.toml").write_text(f'[project]\nname="search-swe"\nversion="{version}"\n')
        self.task(self.source, "second-search")
        self.commit(self.source)
        return self.git(self.source, "rev-parse", "HEAD")

    def test_shallow_update_discovers_new_tasks_and_preserves_ignored_inputs(self):
        env = self.checkout / ".env"
        env.write_text("PRIVATE_FIXTURE_KEY=keep-me\n")
        data = self.checkout / "tasks/first-search/data/input"
        data.parent.mkdir()
        data.write_text("downloaded input")
        job = self.checkout / "jobs/old/result.json"
        job.parent.mkdir(parents=True)
        job.write_text('{"score":1}')
        target = self.advance()
        result = updates.update(self.checkout)
        self.assertTrue(result["updated"])
        self.assertEqual(result["tasks_added"], ["second-search"])
        self.assertEqual(result["task_count_after"], 2)
        self.assertEqual(self.git(self.checkout, "rev-parse", "HEAD"), target)
        self.assertEqual(set(repository.discover(self.checkout)), {"first-search", "second-search"})
        self.assertEqual(env.read_text(), "PRIVATE_FIXTURE_KEY=keep-me\n")
        self.assertEqual(data.read_text(), "downloaded input")
        self.assertEqual(job.read_text(), '{"score":1}')
        self.assertFalse(updates.update(self.checkout)["updated"])

    def test_check_fetches_without_changing_dirty_checkout_files(self):
        head = self.git(self.checkout, "rev-parse", "HEAD")
        modified = self.checkout / "scripts/evaluation/run_task.py"
        modified.write_text("# local edit\n")
        self.advance()
        result = updates.update(self.checkout, check=True)
        self.assertEqual(result["status"], "available")
        self.assertTrue(result["dirty"])
        self.assertFalse(result["updated"])
        self.assertEqual(self.git(self.checkout, "rev-parse", "HEAD"), head)
        self.assertEqual(modified.read_text(), "# local edit\n")
        self.assertFalse((self.checkout / "tasks/second-search").exists())
        with self.assertRaisesRegex(ValueError, "local changes"):
            updates.update(self.checkout)

    def test_another_fetch_cannot_replace_this_updates_target(self):
        expected = self.advance()
        self.git(self.source, "checkout", "-qb", "feature")
        self.task(self.source, "feature-search")
        self.commit(self.source)
        other = self.git(self.source, "rev-parse", "HEAD")
        real_git = updates.git

        def interleaved(root, *arguments, **kwargs):
            result = real_git(root, *arguments, **kwargs)
            if arguments[0] == "fetch":
                self.git(root, "fetch", "--quiet", "origin", "refs/heads/feature")
                self.assertEqual(self.git(root, "rev-parse", "FETCH_HEAD"), other)
            return result

        for check in (True, False):
            with patch.object(updates, "git", side_effect=interleaved):
                result = updates.update(self.checkout, check=check)
            self.assertEqual(result["target"], expected)
            self.assertEqual(result["tasks_added"], ["second-search"])
            self.assertEqual(self.git(self.checkout, "for-each-ref", "--format=%(refname)", "refs/search-swe/"), "")
        self.assertEqual(self.git(self.checkout, "rev-parse", "HEAD"), expected)
        self.assertFalse((self.checkout / "tasks/feature-search").exists())

    def test_untracked_and_staged_changes_block_before_fetch(self):
        local = self.checkout / "notes.txt"
        local.write_text("keep")
        for stage in (False, True):
            if stage:
                self.git(self.checkout, "add", "notes.txt")
            with patch.object(updates, "git", wraps=updates.git) as git, \
                    self.assertRaisesRegex(ValueError, "local changes"):
                updates.update(self.checkout)
            self.assertFalse(any(call.args[1] == "fetch" for call in git.call_args_list))
        self.assertEqual(local.read_text(), "keep")

    def test_diverged_history_is_reported_and_preserved(self):
        (self.checkout / "local.txt").write_text("local commit")
        self.commit(self.checkout)
        head = self.git(self.checkout, "rev-parse", "HEAD")
        self.advance()
        result = updates.update(self.checkout, check=True)
        self.assertEqual((result["status"], result["ahead"], result["behind"]), ("diverged", 1, 1))
        with self.assertRaisesRegex(ValueError, "diverged"):
            updates.update(self.checkout)
        self.assertEqual(self.git(self.checkout, "rev-parse", "HEAD"), head)

    def test_local_commits_ahead_of_upstream_are_retained(self):
        (self.checkout / "local.txt").write_text("local commit")
        self.commit(self.checkout)
        result = updates.update(self.checkout)
        self.assertEqual(result["status"], "ahead")
        self.assertFalse(result["updated"])

    def test_incompatible_upstream_is_detected_before_fast_forward(self):
        head = self.git(self.checkout, "rev-parse", "HEAD")
        self.advance("0.4.0")
        self.assertEqual(updates.update(self.checkout, check=True)["status"], "incompatible")
        with self.assertRaisesRegex(ValueError, "incompatible with CLI"):
            updates.update(self.checkout)
        self.assertEqual(self.git(self.checkout, "rev-parse", "HEAD"), head)
        self.assertEqual(repository.checkout_version(self.checkout), "0.3.0")
        self.assertEqual(self.git(self.checkout, "for-each-ref", "--format=%(refname)", "refs/search-swe/"), "")

    def test_configured_upstream_and_removed_tasks_are_respected(self):
        self.git(self.source, "checkout", "-qb", "release")
        self.git(self.checkout, "remote", "rename", "origin", "tasks-source")
        self.git(self.checkout, "config", "remote.tasks-source.fetch", "+refs/heads/*:refs/remotes/tasks-source/*")
        self.git(self.checkout, "fetch", "--quiet", "tasks-source")
        self.git(self.checkout, "config", "branch.main.merge", "refs/heads/release")
        shutil.rmtree(self.source / "tasks/first-search")
        self.advance()
        result = updates.update(self.checkout)
        self.assertEqual(result["tasks_removed"], ["first-search"])
        self.assertEqual(result["tasks_added"], ["second-search"])
        self.assertEqual(self.git(self.checkout, "symbolic-ref", "--short", "HEAD"), "main")
        self.assertEqual(set(repository.discover(self.checkout)), {"second-search"})

    def test_missing_upstream_launcher_is_rejected(self):
        (self.source / "scripts/evaluation/run_task.py").unlink()
        self.commit(self.source)
        head = self.git(self.checkout, "rev-parse", "HEAD")
        with self.assertRaisesRegex(ValueError, "incompatible"):
            updates.update(self.checkout)
        self.assertEqual(self.git(self.checkout, "rev-parse", "HEAD"), head)

    def test_update_can_repair_an_older_checkout_series(self):
        project = self.source / "pyproject.toml"
        project.write_text('[project]\nname="search-swe"\nversion="0.1.0"\n')
        self.commit(self.source)
        older = self.root / "older"
        subprocess.run(["git", "clone", "--quiet", self.source.as_uri(), str(older)], check=True, capture_output=True)
        self.assertFalse(updates.info(older)["compatible"])
        self.advance()
        with redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(["update", "--repo", str(older), "--json"]), 0)
        self.assertTrue(json.loads(output.getvalue())["updated"])
        self.assertTrue(updates.info(older)["compatible"])

    def test_detached_head_missing_upstream_and_unfinished_operation(self):
        self.git(self.checkout, "checkout", "--quiet", "--detach")
        with self.assertRaisesRegex(ValueError, "detached HEAD"):
            updates.update(self.checkout)
        self.git(self.checkout, "checkout", "--quiet", "main")
        marker = self.checkout / ".git/MERGE_HEAD"
        marker.write_text(self.git(self.checkout, "rev-parse", "HEAD") + "\n")
        with self.assertRaisesRegex(ValueError, "unfinished Git operation"):
            updates.update(self.checkout)
        self.assertTrue(updates.update(self.checkout, check=True)["git_operation_in_progress"])
        marker.unlink()
        self.git(self.checkout, "branch", "--unset-upstream")
        with self.assertRaisesRegex(ValueError, "no upstream"):
            updates.update(self.checkout)

    def test_upstream_cannot_overwrite_ignored_credentials(self):
        (self.checkout / ".env").write_text("keep-private\n")
        (self.source / ".env").write_text("upstream file\n")
        self.git(self.source, "add", "--force", ".env")
        self.commit(self.source)
        head = self.git(self.checkout, "rev-parse", "HEAD")
        with self.assertRaises(ValueError):
            updates.update(self.checkout)
        self.assertEqual(self.git(self.checkout, "rev-parse", "HEAD"), head)
        self.assertEqual((self.checkout / ".env").read_text(), "keep-private\n")

    def test_info_works_without_git_docker_credentials_or_network(self):
        archive = self.root / "archive"
        shutil.copytree(self.checkout, archive, ignore=shutil.ignore_patterns(".git"))
        with patch.object(updates.shutil, "which", return_value=None), \
                patch("search_swe.cli.runner.doctor", side_effect=AssertionError("Docker queried")), \
                redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(["--repo", str(archive), "info", "--json"]), 0)
        result = json.loads(output.getvalue())
        self.assertEqual(result["cli_version"], __version__)
        self.assertEqual(result["task_count"], 1)
        self.assertIsNone(result["git"])
        with self.assertRaisesRegex(ValueError, "requires Git"):
            updates.update(archive)

    def test_json_check_and_errors_keep_credentials_out_of_output(self):
        self.advance()
        with redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(["update", "--repo", str(self.checkout), "--check", "--json"]), 0)
        self.assertEqual(json.loads(output.getvalue())["status"], "available")
        result = subprocess.CompletedProcess([], 128, "", "https://user:private-token@host/repo failed")
        with patch.object(updates.subprocess, "run", return_value=result), \
                self.assertRaises(ValueError) as caught:
            updates.git(self.checkout, "fetch", "origin")
        self.assertNotIn("private-token", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
