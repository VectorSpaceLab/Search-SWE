"""Keep supervisor budgets large enough for every advertised candidate stage."""
import json
from pathlib import Path
import re
import tomllib
import unittest


class BudgetTests(unittest.TestCase):
    def test_nested_budgets_leave_time_for_scoring_and_cleanup(self):
        tests = Path(__file__).resolve().parent
        contract = json.loads((tests / 'runtime_contract.json').read_text())
        script = (tests / 'test.sh').read_text()
        primary = int(re.search(r'--kill-after=15s (\d+)s /opt/conda/bin/python /tests/grader.py', script)[1])
        audit = int(re.search(r'--kill-after=15s (\d+)s /opt/conda/bin/python /tests/run_audit.py', script)[1])
        finalize = int(re.search(r'--kill-after=5s (\d+)s /opt/conda/bin/python /tests/finalize_reward.py', script)[1])
        required = (contract['checkpoint_timeout_sec'] + contract['build_timeout_sec']
                    + contract['query_batches'] * contract['run_timeout_sec'])
        self.assertGreaterEqual(primary - required, 900)
        config_path = tests.parent / 'task.toml'
        if config_path.exists():
            outer = tomllib.loads(config_path.read_text())['verifier']['timeout_sec']
            self.assertGreaterEqual(outer - primary - audit - finalize - 35, 600)
        session = tomllib.loads((tests / 'jailbreak_judge/codex.toml').read_text())['judge']['timeout']
        self.assertGreaterEqual(audit - session, 300)


if __name__ == '__main__':
    unittest.main()
