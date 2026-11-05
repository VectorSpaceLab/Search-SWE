import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from judge_repeats import run_repeated_judge


class RepeatedJudgeTests(unittest.TestCase):
    def run_fake(self, values, failure=None):
        root = tempfile.TemporaryDirectory()
        self.addCleanup(root.cleanup)
        output = Path(root.name)/"reward.json"
        seen = []
        def judge():
            import sys
            number = len(seen)
            destination = Path(sys.argv[sys.argv.index("--output")+1])
            seen.append((os.getpid(), destination, os.environ["REWARDKIT_LOG_DIR"]))
            if failure == number:
                raise RuntimeError("simulated API failure")
            value = values[number]
            destination.write_text(json.dumps({"integrity_judge": value}))
            destination.with_name("reward-details.json").write_text(json.dumps({
                "integrity_judge": {"score": value, "judge_output": "simulated judgment",
                    "criteria": [{"name": "integrity", "raw": "yes" if value else "no", "value": value}]}
            }))
        import sys
        previous_argv = sys.argv
        with patch.dict(os.environ, {"REWARDKIT_LOG_DIR": "original-log-dir"}):
            status = run_repeated_judge(judge, ["judge", "--output", str(output)])
            self.assertEqual(os.environ["REWARDKIT_LOG_DIR"], "original-log-dir")
        self.assertIs(sys.argv, previous_argv)
        return status, output, seen

    def test_three_fresh_reports_and_arithmetic_mean(self):
        status, output, seen = self.run_fake([1, 1, 0])
        self.assertEqual(status, 0)
        self.assertEqual(len(seen), 3)
        self.assertEqual({row[0] for row in seen}, {os.getpid()})
        self.assertEqual(len({row[1] for row in seen}), 3)
        self.assertEqual(len({row[2] for row in seen}), 3)
        self.assertAlmostEqual(json.loads(output.read_text())["integrity_judge"], 2/3)
        detail = json.loads(output.with_name("reward-details.json").read_text())["integrity_judge"]
        self.assertAlmostEqual(detail["criteria"][0]["raw"], 2/3)
        self.assertAlmostEqual(detail["criteria"][0]["value"], 2/3)

    def test_one_failed_measurement_invalidates_average(self):
        status, output, seen = self.run_fake([1, 1, 1], failure=1)
        self.assertEqual(status, 1)
        self.assertEqual(len(seen), 3)
        self.assertEqual(json.loads(output.read_text()), {})
        self.assertFalse(json.loads(output.with_name("judge-repeats.json").read_text())["healthy"])

    def test_all_accept_and_all_reject_are_healthy(self):
        for value in [0, 1]:
            with self.subTest(value=value):
                status, output, seen = self.run_fake([value]*3)
                self.assertEqual(status, 0)
                self.assertEqual(json.loads(output.read_text())["integrity_judge"], value)

    def test_nonbinary_and_nan_results_are_invalid(self):
        for value in [0.5, float("nan"), "yes", None]:
            with self.subTest(value=value):
                status, output, seen = self.run_fake([1, value, 1])
                self.assertEqual(status, 1)
                self.assertEqual(len(seen), 3)
                self.assertEqual(json.loads(output.read_text()), {})

    def test_native_cli_is_invoked_three_times(self):
        import runpy
        import sys
        import rewardkit.__main__ as cli
        runner = Path(__file__).with_name('judge_repeats.py')
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)/'reward.json'
            calls = []
            def native_run(tests_dir, *, workspace, output, **kwargs):
                calls.append((tests_dir, workspace, str(output)))
                value = 0 if len(calls) == 2 else 1
                Path(output).write_text(json.dumps({'integrity_judge': value}))
                Path(output).with_name('reward-details.json').write_text(json.dumps({
                    'integrity_judge': {'kind': 'group', 'score': value, 'components': [
                        {'name': 'integrity', 'detail': {'kind': 'agent', 'score': value,
                            'judge_output': 'offline native CLI fixture', 'criteria': [
                                {'name': 'integrity', 'raw': 'yes' if value else 'no', 'value': value}]}}]}}))
                return {'integrity_judge': value}
            with patch.object(cli, 'run', side_effect=native_run), patch.object(sys, 'argv', [
                str(runner), str(runner.with_name('rewardkit_deepseek.py')), '/audit/config', '--workspace', '/audit/submission', '--output', str(output)]):
                with self.assertRaises(SystemExit) as result:
                    runpy.run_path(str(runner), run_name='__main__')
            self.assertEqual(result.exception.code, 0)
            self.assertEqual(len(calls), 3)
            self.assertTrue(all(call[:2] == ('/audit/config', '/audit/submission') for call in calls))
            self.assertAlmostEqual(json.loads(output.read_text())['integrity_judge'], 2/3)
