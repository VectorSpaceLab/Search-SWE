"""The isolated grader must import its trusted fixed scoring parameters."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class GraderImportTests(unittest.TestCase):
    def test_fixed_parameters_import_under_isolated_python(self):
        grade = Path(__file__).with_name("grade.py").resolve()
        probe = """
import pathlib, runpy, sys, types
def forbidden(*args, **kwargs):
    raise AssertionError('The import probe must not run evaluation or cleanup')
for name, attribute in [('evaluate', 'evaluate'), ('metrics', 'reward'), ('isolation', 'cleanup')]:
    module = types.ModuleType(name)
    setattr(module, attribute, forbidden)
    sys.modules[name] = module
runpy.run_path(sys.argv[1], run_name='grade_import_probe')
assert pathlib.Path(sys.modules['scoring_parameters'].__file__).resolve() == pathlib.Path(sys.argv[1]).with_name('scoring_parameters.py')
"""
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "scoring_parameters.py").write_text(
                "raise AssertionError('Untrusted working-directory module was imported')\n"
            )
            result = subprocess.run(
                [sys.executable, "-I", "-B", "-c", probe, str(grade)],
                cwd=directory, env={**os.environ, "PYTHONPATH": directory},
                capture_output=True, text=True, timeout=30,
            )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
