"""Exercise the real supervisor orchestration with offline timed-worker fixtures."""

import sys
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(TASK_ROOT / "tests"))

import json
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import evaluate


class TimingRepeatTests(unittest.TestCase):
    def run_fixture(self, changed=False, failed_reference=False):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            submission = root / 'submission'
            submission.mkdir()
            (submission / 'run.sh').write_text('#!/bin/sh\n')
            (submission / 'run.sh').chmod(0o755)
            query = root / 'query.jsonl'
            query.write_text('{}\n')
            def path(value):
                return submission if str(value) == '/app/submission' else Path(value)
            copyfile = evaluate.shutil.copyfile
            def copy(source, target, **kwargs):
                return copyfile(query if str(source) == '/tests/data/queries.jsonl' else source, target, **kwargs)
            counts = {'quality': 0, 'reference': 0, 'candidate': 0}
            def timed(command, *_args, **_kwargs):
                kind = ('quality' if '--fit' in command else
                        'reference' if command[0] == '/tests/time_reference/run.sh' else 'candidate')
                index = counts[kind]
                counts[kind] += 1
                output = Path(command[command.index('--output') + 1])
                output.write_text('changed\n' if changed and kind == 'candidate' and index == 4 else '{}\n')
                if '--report' in command:
                    Path(command[command.index('--report') + 1]).write_text('{}')
                seconds = {'quality': [1], 'reference': [10, 20, 30, 40, 300], 'candidate': [1, 2, 3, 4, 30]}[kind][index]
                return {'status': 124 if failed_reference and kind == 'reference' and index == 4 else 0,
                        'elapsed_seconds': seconds, 'cleanup_seconds': 0, 'background_processes': False}
            def run(command, **kwargs):
                if 'pgrep' in command:
                    return subprocess.CompletedProcess(command, 1)
                self.environment = kwargs['env']
                return subprocess.CompletedProcess(command, 0)
            with patch.multiple(evaluate, WORK=root/'work', LOG=root/'logs', Path=path), \
                    patch.object(evaluate.shutil, 'copyfile', side_effect=copy), \
                    patch.object(evaluate, 'run_timed', side_effect=timed), \
                    patch.object(evaluate, 'stop_submission'), \
                    patch.object(evaluate.os, 'chown'), \
                    patch.object(Path, 'chmod'), \
                    patch.object(evaluate.subprocess, 'run', side_effect=run):
                evaluate.main()
            samples = json.loads((root/'logs/timing-samples.json').read_text())
            timers = {name: float((root/'work/private'/f'{name}-time.txt').read_text())
                      for name in ('starter', 'candidate') if (root/'work/private'/f'{name}-time.txt').exists()}
            return counts, samples, timers, self.environment

    def test_one_fit_five_timed_runs_and_median(self):
        counts, samples, timers, env = self.run_fixture()
        self.assertEqual(counts, {'quality': 1, 'reference': 5, 'candidate': 5})
        self.assertEqual(timers, {'starter': 30., 'candidate': 3.})
        self.assertEqual(samples['candidate'], [1, 2, 3, 4, 30])
        self.assertEqual(env['SEARCH_SWE_EXECUTION_ERROR'], '')

    def test_fifth_candidate_must_still_be_deterministic(self):
        _, _, timers, env = self.run_fixture(changed=True)
        self.assertIn('not deterministic', env['SEARCH_SWE_EXECUTION_ERROR'])
        self.assertEqual(env['SEARCH_SWE_ERROR_KIND'], 'candidate')
        self.assertEqual(timers, {})

    def test_reference_failure_is_not_a_candidate_score(self):
        counts, _, timers, env = self.run_fixture(failed_reference=True)
        self.assertEqual(counts, {'quality': 1, 'reference': 5, 'candidate': 4})
        self.assertIn('reference failed', env['SEARCH_SWE_EXECUTION_ERROR'])
        self.assertEqual(env['SEARCH_SWE_ERROR_KIND'], 'infrastructure')
        self.assertEqual(timers, {})


if __name__ == '__main__':
    unittest.main()
