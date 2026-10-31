import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from search_swe import repository, wizard
from search_swe.cli import main


class RepositoryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.enterContext(patch.dict(os.environ, {"HOME": str(self.home),
            "XDG_CONFIG_HOME": str(self.root / "config"), "SEARCH_SWE_REPO": ""}))
        self.enterContext(patch.object(repository, "__file__", str(self.root / "installed/search_swe/repository.py")))
        self.enterContext(patch("pathlib.Path.cwd", return_value=self.home))
        self.enterContext(redirect_stdout(io.StringIO()))
        self.enterContext(redirect_stderr(io.StringIO()))
        for name in ("select", "path", "confirm"):
            self.enterContext(patch.object(wizard.questionary, name))

    def checkout(self, path):
        (path / "tasks").mkdir(parents=True)
        (path / "tasks/.keep").touch()
        (path / "scripts").mkdir()
        (path / "scripts/run_task.py").write_text("# fixture\n")
        return path.resolve()

    def test_saved_path_is_reused_and_explicit_or_current_paths_take_precedence(self):
        saved = self.checkout(self.root / "saved")
        current = self.checkout(self.root / "current")
        explicit = self.checkout(self.root / "explicit")
        repository.remember_repo(saved)
        self.assertEqual(repository.find_repo(), saved)
        with patch("pathlib.Path.cwd", return_value=current / "tasks"):
            self.assertEqual(repository.find_repo(), current)
            with patch.dict(os.environ, {"SEARCH_SWE_REPO": str(saved)}):
                self.assertEqual(repository.find_repo(), saved)
                self.assertEqual(repository.find_repo(explicit), explicit)
        self.assertEqual(json.loads(repository.preference_path().read_text()), {"repo": str(saved)})

    def test_bad_explicit_path_does_not_fall_back_to_saved_checkout(self):
        repository.remember_repo(self.checkout(self.root / "saved"))
        with self.assertRaises(ValueError):
            repository.find_repo(self.root / "missing")
        with patch.dict(os.environ, {"SEARCH_SWE_REPO": str(self.root / "missing")}):
            with self.assertRaises(ValueError):
                repository.find_repo()

    def test_missing_stale_and_invalid_preferences_allow_setup_again(self):
        path = repository.preference_path()
        path.parent.mkdir(parents=True)
        for content in ('{"repo": "/nonexistent/search-swe-fixture"}', '[]', '{bad', '{"repo": 1}'):
            path.write_text(content)
            self.assertIsNone(repository.saved_repo())
            with self.assertRaises(ValueError):
                repository.find_repo()

    def test_select_existing_remembers_it_without_git_or_changes_to_checkout(self):
        existing = self.checkout(self.root / "existing")
        with patch.object(wizard, "ask", side_effect=["existing", str(existing)]), \
                patch.object(wizard, "clone_repo") as clone:
            self.assertEqual(wizard.select_repository(), existing)
        clone.assert_not_called()
        self.assertEqual(repository.find_repo(), existing)
        self.assertFalse((existing / ".env").exists())

    def test_default_existing_checkout_is_reused(self):
        existing = self.checkout(self.home / "Search-SWE")
        with patch.object(wizard, "ask", return_value="default"), patch.object(wizard, "clone_repo") as clone:
            self.assertEqual(wizard.select_repository(), existing)
        clone.assert_not_called()

    def test_default_clone_requires_acceptance_and_remembers_destination(self):
        with patch.object(wizard, "ask", side_effect=["default", True]), \
                patch.object(wizard, "clone_repo", side_effect=self.checkout) as clone:
            self.assertEqual(wizard.select_repository(), self.home / "Search-SWE")
        clone.assert_called_once_with(self.home / "Search-SWE")
        self.assertEqual(repository.saved_repo(), self.home / "Search-SWE")

    def test_custom_clone_uses_expanded_destination(self):
        with patch.object(wizard, "ask", side_effect=["custom", "~/benchmarks/Search SWE", True]), \
                patch.object(wizard, "clone_repo", side_effect=self.checkout) as clone:
            self.assertEqual(wizard.select_repository(), self.home / "benchmarks/Search SWE")
        clone.assert_called_once_with(self.home / "benchmarks/Search SWE")

    def test_declining_clone_and_cancel_do_not_write_preferences_or_create_destination(self):
        for responses in (["default", False], KeyboardInterrupt):
            with patch.object(wizard, "ask", side_effect=responses), \
                    patch.object(wizard, "clone_repo") as clone, self.assertRaises(KeyboardInterrupt):
                wizard.select_repository()
            clone.assert_not_called()
            self.assertFalse(repository.preference_path().exists())
            self.assertFalse((self.home / "Search-SWE").exists())

    def test_nonempty_destination_is_preserved_and_user_can_choose_another(self):
        default = self.home / "Search-SWE"
        default.mkdir()
        sentinel = default / "important.txt"
        sentinel.write_text("keep")
        existing = self.checkout(self.root / "existing")
        with patch.object(wizard, "ask", side_effect=["default", "existing", str(existing)]), \
                patch.object(wizard, "clone_repo") as clone:
            self.assertEqual(wizard.select_repository(), existing)
        clone.assert_not_called()
        self.assertEqual(sentinel.read_text(), "keep")
        with patch.object(repository.subprocess, "run") as run, self.assertRaises(ValueError):
            repository.clone_repo(default)
        run.assert_not_called()

    def test_failed_clone_does_not_remember_destination(self):
        with patch.object(wizard, "ask", side_effect=["default", True]), \
                patch.object(wizard, "clone_repo", side_effect=subprocess.CalledProcessError(128, "git")), \
                self.assertRaises(subprocess.CalledProcessError):
            wizard.select_repository()
        self.assertFalse(repository.preference_path().exists())

    def test_offline_setup_offers_existing_checkouts_only(self):
        existing = self.checkout(self.root / "existing")
        with patch.object(wizard, "ask", side_effect=["existing", str(existing)]), \
                patch.object(wizard, "clone_repo") as clone:
            self.assertEqual(wizard.select_repository(offline=True), existing)
        choices = wizard.questionary.select.call_args.kwargs["choices"]
        self.assertEqual([choice.value for choice in choices], ["existing"])
        clone.assert_not_called()

    def test_read_only_preferences_do_not_prevent_using_selected_checkout(self):
        existing = self.checkout(self.root / "existing")
        with patch.object(wizard, "ask", side_effect=["existing", str(existing)]), \
                patch.object(wizard, "remember_repo", side_effect=PermissionError("read only")):
            self.assertEqual(wizard.select_repository(), existing)

    def test_real_git_clone_with_local_origin_and_nested_destination(self):
        origin = self.checkout(self.root / "origin")
        for args in (["init", "-q", "-b", "main"], ["add", "."],
                     ["-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                      "-c", "commit.gpgsign=false", "commit", "-qm", "Fixture"]):
            subprocess.run(["git", "-C", str(origin), *args], check=True, capture_output=True)
        destination = self.root / "nested/path with spaces/checkout"
        with patch.object(repository, "REPOSITORY_URL", origin.as_uri()):
            self.assertEqual(repository.clone_repo(destination), destination)
        self.assertEqual((destination / "scripts/run_task.py").read_text(), "# fixture\n")
        self.assertTrue((destination / ".git").is_dir())

    def test_cli_bootstraps_interactive_run_and_configure_only(self):
        for command in (["run"], ["configure"], []):
            with patch("search_swe.cli.find_repo", side_effect=ValueError("missing")), \
                    patch("sys.stdin.isatty", return_value=True), patch("sys.stdout.isatty", return_value=True), \
                    patch.object(wizard, "select_repository", return_value=self.root) as choose, \
                    patch("search_swe.cli.configure_run", return_value=0) as configure:
                self.assertEqual(main(command), 0)
            choose.assert_called_once_with(offline=False)
            self.assertEqual(configure.call_args.args[1], self.root)

    def test_cli_noninteractive_dry_run_and_explicit_path_never_bootstrap(self):
        for args in (["run", "--yes"], ["run", "--dry-run"], ["configure", "--yes"],
                     ["list"], ["doctor"], ["run", "--repo", "/missing"]):
            with patch("search_swe.cli.find_repo", side_effect=ValueError("missing")), \
                    patch("sys.stdin.isatty", return_value=True), patch("sys.stdout.isatty", return_value=True), \
                    patch.object(wizard, "select_repository") as choose:
                self.assertEqual(main(args), 1)
            choose.assert_not_called()
        with patch("search_swe.cli.find_repo", side_effect=ValueError("missing")), \
                patch("sys.stdin.isatty", return_value=False), patch.object(wizard, "select_repository") as choose:
            self.assertEqual(main(["run"]), 1)
        choose.assert_not_called()


if __name__ == "__main__":
    unittest.main()
