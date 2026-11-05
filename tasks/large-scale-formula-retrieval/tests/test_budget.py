"""Every documented restart path must fit the primary and outer supervisors."""
from pathlib import Path
import re
import tomllib
import unittest

from repetition import REPEATS, BUILD_TIMEOUT, LOAD_TIMEOUT, WARMUP_TIMEOUT, QUERY_TIMEOUT


class BudgetTests(unittest.TestCase):
    def test_five_passes_with_query_restarts_fit(self):
        tests = Path(__file__).resolve().parent
        entry = (tests / 'test.sh').read_text()
        primary = int(re.search(r'--kill-after=10s (\d+)s /opt/conda/bin/python /tests/grader.py', entry)[1])
        audit = int(re.search(r'--kill-after=30s (\d+)s /opt/conda/bin/python /tests/run_audit.py', entry)[1])
        finalize = int(re.search(r'--kill-after=5s (\d+)s /opt/conda/bin/python /tests/integrity_gate.py', entry)[1])
        calls = 76 * REPEATS
        stages = BUILD_TIMEOUT + calls * (LOAD_TIMEOUT + WARMUP_TIMEOUT + QUERY_TIMEOUT)
        cleanup = (calls + 1) * 11
        self.assertGreaterEqual(primary - stages - cleanup, 600)
        session = tomllib.loads((tests / 'jailbreak_judge/codex.toml').read_text())['judge']['timeout']
        self.assertGreaterEqual(audit - session, 100)
        config_path = tests.parent / 'task.toml'
        if config_path.exists():
            config = tomllib.loads(config_path.read_text())
            self.assertEqual(config['metadata']['query_repeats'], REPEATS)
            self.assertGreaterEqual(config['verifier']['timeout_sec'] - primary - audit - finalize - 45, 500)


if __name__ == '__main__':
    unittest.main()
