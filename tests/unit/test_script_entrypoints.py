"""Check organized checkout tools in both supported Python execution modes."""

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
ENTRYPOINTS = (
    "evaluation/run_task.py",
    "evaluation/task_storage.py",
    "assets/download_assets.py",
    "assets/download_models.py",
    "assets/prepare_hf_upload.py",
    "validation/check_release.py",
    "validation/check_tasks.py",
    "egress/build_egress_component.py",
    "egress/build_egress_gateway.py",
    "egress/egress_cleanup.py",
)


class ScriptEntrypoints(unittest.TestCase):
    def test_help_by_absolute_path_from_another_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            for name in ENTRYPOINTS:
                with self.subTest(script=name):
                    result = subprocess.run(
                        [sys.executable, str(ROOT / "scripts" / name), "--help"],
                        cwd=directory, capture_output=True, text=True, timeout=30,
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertIn("usage:", result.stdout)

    def test_help_as_repository_module(self):
        for name in ENTRYPOINTS:
            module = "scripts." + name.removesuffix(".py").replace("/", ".")
            with self.subTest(module=module):
                result = subprocess.run(
                    [sys.executable, "-m", module, "--help"],
                    cwd=ROOT, capture_output=True, text=True, timeout=30,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("usage:", result.stdout)
