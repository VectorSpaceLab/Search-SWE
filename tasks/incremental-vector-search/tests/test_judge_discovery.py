"""Exercise RewardKit discovery with only the verifier's packaged files."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


class JudgeDiscoveryTests(unittest.TestCase):
    def test_discovery_without_authoring_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tests = root / "tests"
            shutil.copytree(Path(__file__).resolve().parent, tests,
                            ignore=shutil.ignore_patterns("__pycache__"))
            self.assertFalse((root / "prepare_data.py").exists())
            self.assertFalse((root / "assets.json").exists())
            # Isolate RewardKit's registration state from unittest discovery.
            result = subprocess.run(
                [sys.executable, "-c", """
import json
import sys
sys.path.insert(0, sys.argv[1])
import rewardkit_deepseek
from rewardkit.runner import _discover_layout
layout = _discover_layout(sys.argv[1], workspace=sys.argv[2])
print(json.dumps([group.name for group in layout.groups]))
""", str(tests), str(root)],
                capture_output=True, text=True, timeout=60,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(json.loads(result.stdout), ["integrity_judge"])


if __name__ == "__main__":
    unittest.main()
