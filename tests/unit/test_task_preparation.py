"""Preparation must complete before launch and supply per-run settings."""
import json
import os
from pathlib import Path
import tempfile
import unittest

from scripts.evaluation.task_preparation import prepare_task


class PreparationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.task = Path(temporary.name) / 'tasks/example-search'
        (self.task / 'tools').mkdir(parents=True)
        self.helper = self.task / 'tools/prepare_task.py'

    def test_tasks_without_a_hook_do_not_change(self):
        env = {'UNCHANGED': 'value'}
        prepare_task(self.task, env)
        self.assertEqual(env, {'UNCHANGED': 'value'})

    def test_real_hook_receives_cpu_allocation_and_returns_settings(self):
        self.helper.write_text('''import argparse,json
from pathlib import Path
p=argparse.ArgumentParser()
p.add_argument('--result-json',type=Path)
p.add_argument('--cpu-set')
a=p.parse_args()
a.result_json.write_text(json.dumps({'environment': {'FIXTURE_CPUSET': a.cpu_set, 'FIXTURE_PLATFORM_ROOT': '/prepared/cache'}}))
''')
        env = dict(os.environ)
        prepare_task(self.task, env, cpu_set='20-35')
        self.assertEqual(env['FIXTURE_CPUSET'], '20-35')
        self.assertEqual(env['FIXTURE_PLATFORM_ROOT'], '/prepared/cache')

    def test_failed_hook_cannot_supply_a_successful_preparation(self):
        self.helper.write_text('raise SystemExit(7)\n')
        with self.assertRaisesRegex(RuntimeError, 'evaluation was not started'):
            prepare_task(self.task, dict(os.environ))

    def test_malformed_environment_is_rejected(self):
        self.helper.write_text('''import json,sys
from pathlib import Path
Path(sys.argv[2]).write_text(json.dumps({'environment': {'INVALID': 17}}))
''')
        with self.assertRaisesRegex(ValueError, 'invalid environment'):
            prepare_task(self.task, dict(os.environ))


if __name__ == '__main__':
    unittest.main()
