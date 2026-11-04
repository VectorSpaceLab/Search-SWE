"""Public permission checks use temporary fixtures and never change /app."""
import contextlib
import importlib.util
import io
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

TASK_ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "public_runtime_check", TASK_ROOT / "environment/tools/check_runtime.py")
helper = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(helper)


class PermissionCheckTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.index = self.root / "check/index"
        self.index.mkdir(parents=True)
        self.output = self.root / "check/output/results.jsonl"
        self.app = self.root / "app"
        self.app.mkdir()
        (self.app / "run.sh").write_text("#!/bin/sh\nexit 0\n")
        (self.app / "run.sh").chmod(0o755)
        (self.index / "vectors").write_text("fixture")
        (self.index / "helper.sh").write_text("#!/bin/sh\nexit 0\n")
        (self.index / "helper.sh").chmod(0o755)

    def mode(self, path):
        return stat.S_IMODE(path.stat().st_mode)

    def prepare(self, readonly):
        with patch.object(helper.os, "chown"):
            return helper.prepare_permissions(
                self.index, self.output, readonly=readonly, app=self.app)

    def test_query_freezes_index_without_marker_and_keeps_scratch_writable(self):
        self.prepare(readonly=False)
        _, _, home = self.prepare(readonly=True)
        self.assertEqual(self.mode(self.index), 0o550)
        self.assertEqual(self.mode(self.index / "vectors"), 0o440)
        self.assertEqual(self.mode(self.index / "helper.sh"), 0o550)
        self.assertEqual(self.mode(self.index / "tmp"), 0o550)
        self.assertEqual(home, self.output.parent)
        self.assertEqual(self.mode(home), 0o750)
        self.assertEqual(self.mode(home / "tmp"), 0o700)
        self.assertEqual(self.mode(self.app / "run.sh"), 0o550)

    def test_build_can_write_index_but_not_code_or_index_parent(self):
        _, _, home = self.prepare(readonly=False)
        self.assertEqual(home, self.index)
        self.assertEqual(self.mode(self.index), 0o750)
        self.assertEqual(self.mode(self.index / "vectors"), 0o640)
        self.assertEqual(self.mode(self.index.parent), 0o711)
        self.assertEqual(self.mode(self.app), 0o550)

    def test_overlapping_output_is_rejected_before_any_permission_change(self):
        for output in [self.index / "results.jsonl",
                       self.index / "nested/results.jsonl",
                       self.index.parent / "results.jsonl"]:
            with self.subTest(output=output), patch.object(helper.os, "chown") as chown:
                with self.assertRaisesRegex(ValueError, "must not overlap"):
                    helper.prepare_permissions(self.index, output, readonly=True, app=self.app)
                chown.assert_not_called()
        self.assertEqual(self.mode(self.index / "helper.sh"), 0o755)

    def test_output_symlink_into_index_is_rejected(self):
        alias = self.root / "alias"
        alias.symlink_to(self.index, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "must not overlap"):
            helper.checked_paths(self.index, alias / "results.jsonl")

    def test_sibling_with_shared_name_prefix_is_allowed(self):
        output = self.index.parent / "index-output/results.jsonl"
        self.assertEqual(helper.checked_paths(self.index, output), (self.index, output))

    def test_missing_query_argument_does_not_modify_permissions(self):
        with patch.object(helper.os, "geteuid", return_value=0), \
                patch.object(helper, "prepare_permissions") as prepare, \
                contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as error:
                helper.main(["query"])
        self.assertEqual(error.exception.code, 2)
        prepare.assert_not_called()


if __name__ == "__main__":
    unittest.main()
