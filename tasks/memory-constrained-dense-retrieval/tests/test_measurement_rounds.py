"""Exercise five fresh workloads with synthetic data and no privileged processes."""

import contextlib
import io
import json
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest.mock import patch

import grader


class MeasurementRoundTests(unittest.TestCase):
    def run_fixture(self, latencies, misses=None, failures=None, failed_build=None, oom=False):
        misses = misses or {}
        failures = failures or {}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data, private, app, index = [root / name for name in ('data', 'private', 'app', 'index')]
            for path in (data, private, app, index):
                path.mkdir()
            config = {'rows': 4, 'dimension': 1024, 'dtype': 'float32'}
            (data / 'vector_config.json').write_text(json.dumps(config))
            (data / 'vectors.f32').write_bytes(bytes(4 * 1024 * 4))
            (data / 'metadata.jsonl').write_text(''.join(
                json.dumps({'row_id': i, 'doc_id': f'd{i}'}) + '\n' for i in range(4)))
            (private / 'vector_config.json').write_text(json.dumps(config | {'rows': 20}))
            (private / 'query_vectors.f32').write_bytes(bytes(20 * 1024 * 4))
            (private / 'query_metadata.jsonl').write_text(''.join(
                json.dumps({'row_id': i, 'query_id': f'q{i}'}) + '\n' for i in range(20)))
            (private / 'ground_truth.jsonl').write_text(''.join(
                json.dumps({'query_id': f'q{i}', 'relevant_doc_ids': ['d0']}) + '\n' for i in range(20)))
            work, results = root / 'work', root / 'results'
            report_path = results / 'evaluation.json'
            state = {'round': 0, 'service': False, 'ipc': None}
            commands, orders = [], []
            snapshot_calls = 0

            def stop():
                state['service'] = False

            def restart():
                stop()
                state['ipc'] = None

            def resources():
                nonlocal snapshot_calls
                snapshot_calls += 1
                return {'memory.max': str(grader.MEMORY_LIMIT_BYTES), 'memory.swap.max': '0',
                        'memory.events': f'oom_kill {int(oom and snapshot_calls > 1)}'}

            def run_timed(command, *, timeout, **paths):
                commands.append((command, timeout))
                if Path(command[0]).name == 'build.sh':
                    state['round'] += 1
                    self.assertFalse(state['service'])
                    self.assertIsNone(state['ipc'])
                    self.assertEqual({p.name for p in index.iterdir()}, {'tmp', 'cache'})
                    self.assertFalse(any((work / 'input').iterdir()))
                    self.assertFalse(any((work / 'output').iterdir()))
                    (index / 'index.dat').write_text('persisted corpus state')
                    state.update(service=True, ipc='build-only state')
                    orders.append([])
                    return {'returncode': 1 if failed_build == state['round'] else 0,
                            'elapsed_seconds': .01, 'timed_out': False}

                self.assertEqual(command[0], '/usr/local/bin/search-swe-query-cpu')
                metadata = Path(command[command.index('--query-metadata') + 1])
                query_id = json.loads(metadata.read_text())['query_id']
                query_number = int(query_id[1:])
                if not orders[-1]:
                    self.assertFalse(state['service'])
                    self.assertIsNone(state['ipc'])
                else:
                    self.assertTrue(state['service'])
                state.update(service=True, ipc='query cache')
                (index / 'query-cache.bin').write_text('must not survive the next build')
                orders[-1].append(query_id)
                round_number = state['round']
                doc_ids = ['d1', 'd2', 'd3'] if query_number < misses.get(round_number, 0) else ['d0', 'd1', 'd2']
                row = {'query_id': query_id, 'results': [
                    {'doc_id': doc_id, 'score': 3 - i} for i, doc_id in enumerate(doc_ids)]}
                paths['snapshot_path'].write_text(json.dumps(row) + '\n')
                elapsed = latencies[round_number - 1]
                metrics = {'returncode': 0, 'elapsed_seconds': elapsed,
                           'timed_out': elapsed > grader.QUERY_TIMEOUT_SECONDS,
                           'output_error': None}
                metrics.update(failures.get((round_number, query_number), {}))
                return metrics

            with patch.multiple(
                grader, TASK_DATA=data, PRIVATE_DATA=private, SUBMISSION_DIR=app,
                WORK_DIR=work, INPUT_ROOT=work / 'input', OUTPUT_ROOT=work / 'output',
                INDEX_DIR=index, RESULTS_DIR=results, REPORT_PATH=report_path, EXECUTION_ERROR='',
            ), patch.object(grader.os, 'chown'), \
                    patch.object(grader, 'validate_index_workspace', return_value={'capacity_bytes': grader.INDEX_LIMIT_BYTES}), \
                    patch.object(grader, 'check_submission_boundary'), \
                    patch.object(grader, 'validate_query_cpu_boundary', return_value={'allowed_cpus': [0]}), \
                    patch.object(grader, 'resource_snapshot', side_effect=resources), \
                    patch.object(grader, 'restart_submission_for_queries', side_effect=restart), \
                    patch.object(grader, 'stop_submission_processes', side_effect=stop), \
                    patch.object(grader, 'run_timed', side_effect=run_timed), \
                    contextlib.redirect_stdout(io.StringIO()):
                status = grader.main()
            self.assertFalse(state['service'])
            return status, json.loads(report_path.read_text()), commands, orders

    def test_five_fresh_builds_and_same_query_order(self):
        status, report, commands, orders = self.run_fixture([.09, .02, .06, .04, .08])
        self.assertEqual(status, 0)
        self.assertEqual(len(commands), 105)
        self.assertEqual([timeout for command, timeout in commands if Path(command[0]).name == 'build.sh'], [150] * 5)
        self.assertEqual([timeout for command, timeout in commands if command[0].endswith('search-swe-query-cpu')], [.5] * 100)
        self.assertEqual(orders, [[f'q{i}' for i in range(20)]] * 5)
        self.assertEqual(report['query_count'], 20)
        self.assertEqual(report['scoring']['rounds'], 5)
        self.assertEqual(report['selected_round'], 3)
        self.assertEqual(report['scoring']['p95_seconds'], .06)
        self.assertEqual(report['reward'], .5)
        self.assertEqual(len(list({row['round'] for row in report['rounds']})), 5)

    def test_accuracy_comes_from_median_p95_round(self):
        status, report, _, _ = self.run_fixture([.09, .02, .06, .04, .08], misses={3: 1})
        self.assertEqual(status, 0)
        self.assertEqual(report['selected_round'], 3)
        self.assertEqual(report['passed_queries'], 19)
        self.assertEqual(report['primary_metric']['value'], .95)
        self.assertEqual(report['reward'], .475)
        self.assertEqual(report['queries'], report['rounds'][2]['queries'])

    def test_quality_floor_is_preserved(self):
        status, report, _, _ = self.run_fixture([.09, .02, .06, .04, .08], misses={3: 2})
        self.assertEqual(status, 0)
        self.assertEqual(report['primary_metric']['value'], .9)
        self.assertEqual(report['reward'], 0)

    def test_p95_ties_use_round_order_not_accuracy(self):
        status, report, _, _ = self.run_fixture([.06] * 5, misses={3: 1})
        self.assertEqual(status, 0)
        self.assertEqual(report['selected_round'], 3)
        self.assertEqual(report['reward'], .475)

    def test_two_slow_rounds_do_not_determine_latency(self):
        status, report, _, _ = self.run_fixture([.6, .04, .6, .06, .02])
        self.assertEqual(status, 0)
        self.assertEqual(report['selected_round'], 4)
        self.assertEqual(report['scoring']['round_p95_seconds'], [.5, .04, .5, .06, .02])
        self.assertEqual(report['reward'], .5)

    def test_three_timed_out_rounds_fail_quality_floor(self):
        status, report, _, _ = self.run_fixture([.6, .04, .6, .06, .6])
        self.assertEqual(status, 0)
        self.assertEqual(report['scoring']['p95_seconds'], .5)
        self.assertEqual(report['passed_queries'], 0)
        self.assertEqual(report['reward'], 0)

    def test_failed_queries_in_selected_round_receive_no_credit(self):
        for change in ({'returncode': 7}, {'output_error': 'invalid output'}, {'timed_out': True}):
            with self.subTest(change=change):
                status, report, _, _ = self.run_fixture([.09, .02, .06, .04, .08], failures={(3, 0): change})
                self.assertEqual(status, 0)
                self.assertEqual(report['selected_round'], 3)
                self.assertEqual(report['passed_queries'], 19)
                self.assertEqual(report['reward'], .475)

    def test_any_failed_build_still_invalidates_evaluation(self):
        status, report, _, orders = self.run_fixture([.06] * 5, failed_build=2)
        self.assertEqual(status, 1)
        self.assertFalse(report['valid'])
        self.assertEqual(report['reward'], 0)
        self.assertIn('round 2 build.sh', report['errors'][0])
        self.assertEqual(orders, [[f'q{i}' for i in range(20)], []])

    def test_any_oom_still_invalidates_evaluation(self):
        status, report, _, _ = self.run_fixture([.06] * 5, oom=True)
        self.assertEqual(status, 1)
        self.assertFalse(report['valid'])
        self.assertEqual(report['reward'], 0)
        self.assertIn('OOM kill', report['errors'][0])

    def test_incomplete_rounds_cannot_be_selected(self):
        with self.assertRaises(grader.VerificationError):
            grader.select_median_round([])

    def test_repeated_workload_fits_existing_outer_budget(self):
        task = Path(__file__).resolve().parents[1]
        config = tomllib.loads((task / 'task.toml').read_text())
        judge = tomllib.loads((task / 'tests/jailbreak_judge/codex.toml').read_text())
        required = grader.MEASUREMENT_ROUNDS * (grader.BUILD_TIMEOUT_SECONDS +
                   grader.HIDDEN_QUERY_COUNT * grader.QUERY_TIMEOUT_SECONDS) + judge['judge']['timeout'] + 600
        self.assertEqual(config['metadata']['measurement_rounds'], grader.MEASUREMENT_ROUNDS)
        self.assertGreaterEqual(config['verifier']['timeout_sec'], required)


if __name__ == '__main__':
    unittest.main()
