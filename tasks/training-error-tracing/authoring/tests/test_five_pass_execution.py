"""Exercise five real supervisor passes with CPU-only command fixtures."""

import sys
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(TASK_ROOT / "tests"))


import json
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import grade
from efficiency_metrics import quality_gate


class FivePassExecutionTests(unittest.TestCase):
    def run_fixture(self, fail_last=False):
        config = json.loads((TASK_ROOT / "tests" / 'data').joinpath('evaluation-config.json').read_text())
        config.update(raw_efficiency_phase=True, synthetic_fixture_only=True,
                      query_count=2, group_count=1, minimum_queries_per_group=2)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            args = SimpleNamespace(**{name: root / name for name in
                                      ('submission', 'data', 'models', 'private', 'work', 'logs')})
            for path in (args.submission, args.data, args.models, args.private):
                path.mkdir()
            ids = [f'd{i}' for i in range(10)]
            (args.data / 'train.jsonl').write_text(''.join(json.dumps({'id': value}) + '\n' for value in ids))
            queries = [{'id': f'q{i}', 'input_ids': [1, 2, 3], 'target_token_indices': [2],
                        'prompt_token_count': 1} for i in range(2)]
            (args.private / 'queries.jsonl').write_text(''.join(json.dumps(q) + '\n' for q in queries))
            (args.private / 'labels.json').write_text(json.dumps({'group': {
                'record_ids': ids, 'query_ids': [q['id'] for q in queries]}}))
            preparations = []
            requests = []

            def command(argv, **kwargs):
                timed_out = False
                if '--query' in argv:
                    query = json.loads(Path(argv[argv.index('--query') + 1]).read_text())
                    requests.append(query['id'])
                    timed_out = fail_last and len(requests) == 10
                    output = Path(argv[argv.index('--output') + 1])
                    output.write_text(json.dumps({'query_id': query['id'], 'ids': ids}))
                else:
                    preparations.append(argv)
                return {'returncode': 124 if timed_out else 0, 'timed_out': timed_out,
                        'resource_violation': None, 'elapsed_sec': .1, 'processes_before': {}}

            with patch.object(grade, 'require_inspection_capabilities'), \
                    patch.object(grade, 'verify_public_readability'), \
                    patch.object(grade, 'lock_submission'), \
                    patch.object(grade, 'validate_submission_metadata'), \
                    patch.object(grade, 'inventory', return_value={}), \
                    patch.object(grade, 'user_processes', return_value={}), \
                    patch.object(grade, 'signal_services'), \
                    patch.object(grade, 'kill_new_processes'), \
                    patch.object(grade.os, 'chown'), \
                    patch.object(grade.ctypes, 'CDLL', return_value=Mock()), \
                    patch.object(grade, 'run_command', side_effect=command):
                status = grade.main(args, config)
            report = json.loads((args.logs / 'evaluation.json').read_text())
            return status, preparations, requests, report

    def test_one_preparation_and_five_complete_query_passes(self):
        status, preparations, requests, report = self.run_fixture()
        self.assertEqual(status, 0, report)
        self.assertEqual(len(preparations), 1)
        self.assertEqual(len(requests), 10)
        self.assertEqual(len(report['passes']), 5)
        for repetition in range(5):
            rows = [row for row in report['queries'] if row['repetition'] == repetition]
            self.assertEqual({row['id'] for row in rows}, {'q0', 'q1'})
            self.assertEqual(len(rows), 2)
        self.assertTrue(quality_gate(report['passes']))

    def test_fifth_pass_timeout_remains_in_quality_results(self):
        status, _, requests, report = self.run_fixture(fail_last=True)
        self.assertEqual(status, 0, report)
        self.assertEqual(len(requests), 10)
        self.assertEqual(report['queries'][-1]['repetition'], 4)
        self.assertEqual(report['queries'][-1]['execution_error'], 'timeout')
        self.assertFalse(quality_gate(report['passes']))


if __name__ == '__main__':
    unittest.main()
