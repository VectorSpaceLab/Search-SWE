import json
import math
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import grader
import scoring
from finalize_reward import combine


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.order = {str(i): i for i in range(30)}

    def row(self, qid='q', ids=(), scores=None):
        return {'query_id': qid, 'results': [{'doc_id': d, 'score': s} for d, s in
                zip(ids, scores if scores is not None else range(len(ids), 0, -1))]}

    def test_recall_is_not_hit_rate_and_does_not_count_rank_four(self):
        self.assertEqual(scoring.recall_at_3(['0'], {'0', '1'}), .5)
        self.assertEqual(scoring.recall_at_3(['0', '1', '2'], set('01234')), .6)
        self.assertEqual(scoring.recall_at_3(['0', '1', '2', '3'], {'3'}), 0)
        self.assertEqual(scoring.recall_at_3([], {'0'}), 0)

    def test_ceiling_and_linear_normalization(self):
        upper = scoring.recall_ceiling({'a': {'0'}, 'b': set('01234')})
        self.assertAlmostEqual(upper, .8)
        for raw in (0, scoring.BASELINE, scoring.BASELINE - .001):
            self.assertEqual(scoring.normalized_reward(raw, upper), 0)
        self.assertEqual(scoring.normalized_reward(upper, upper), 1)
        self.assertAlmostEqual(scoring.normalized_reward((upper + scoring.BASELINE) / 2, upper), .5)
        for raw in (float('nan'), float('inf'), -.1, upper + .01):
            with self.assertRaises(scoring.VerificationError):
                scoring.normalized_reward(raw, upper)
        with self.assertRaises(scoring.VerificationError):
            scoring.recall_ceiling({'a': set()})

    def test_output_validation(self):
        self.assertEqual(scoring.validate_row(self.row(), 'q', self.order), [])
        self.assertEqual(scoring.validate_row(self.row(ids=['0', '2']), 'q', self.order), ['0', '2'])
        cases = [self.row(ids=['0', '0']), self.row(ids=['missing']),
                 self.row(ids=list('0123')), self.row(ids=['0'], scores=[True]),
                 self.row(ids=['0'], scores=[float('nan')]), self.row(ids=['0'], scores=[float('inf')]),
                 self.row(ids=['0'], scores=['1']), self.row(ids=['0', '1'], scores=[1, 2]),
                 self.row(ids=['1', '0'], scores=[2, 2]), self.row(qid='wrong')]
        for row in cases:
            with self.subTest(row=row), self.assertRaises(scoring.VerificationError):
                scoring.validate_row(row, 'q', self.order)

    def test_strict_json(self):
        for text in ('{"x":1,"x":2}', '{"x":NaN}', '{"x":Infinity}'):
            with self.assertRaises(scoring.VerificationError):
                scoring.strict_json(text)

    def test_batch_coverage_and_arbitrary_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'results'
            path.write_text(json.dumps(self.row('b', ['0'])) + '\n' + json.dumps(self.row('a')) + '\n')
            self.assertEqual(grader.read_output(path, {'a', 'b'}, self.order), {'b': ['0'], 'a': []})
            for data in ([self.row('a')], [self.row('a'), self.row('a')],
                         [self.row('a'), self.row('unknown')], [self.row('a'), {'query_id': []}]):
                path.write_text('\n'.join(map(json.dumps, data)))
                with self.assertRaises(scoring.VerificationError):
                    grader.read_output(path, {'a', 'b'}, self.order)

    def test_output_does_not_follow_symlinks_or_block_on_fifo(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'good').write_text(json.dumps(self.row()) + '\n')
            (root / 'link').symlink_to(root / 'good')
            with self.assertRaises(OSError):
                grader.read_output(root / 'link', {'q'}, self.order)
            os.mkfifo(root / 'fifo')
            with self.assertRaises(scoring.VerificationError):
                grader.read_output(root / 'fifo', {'q'}, self.order)

    def test_build_and_batch_failure_are_fatal(self):
        with mock.patch.object(grader, 'prepare_workspace'), mock.patch.object(grader, 'check_boundary'), \
             mock.patch.object(grader, 'load_data', return_value=(self.order, [], {})), \
             mock.patch.object(grader, 'run_timed', return_value={'timed_out': True, 'returncode': None}):
            with self.assertRaises(scoring.VerificationError):
                grader.evaluate()
        for failure in ({'timed_out': True, 'returncode': 0}, {'timed_out': False, 'returncode': 1}):
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                with mock.patch.object(grader, 'prepare_workspace'), mock.patch.object(grader, 'check_boundary'), \
                     mock.patch.object(grader, 'load_data', return_value=(self.order, [{'query_id': 'q', 'text': 'query'}], {'q': {'0'}})), \
                     mock.patch.object(grader, 'INPUT', root), mock.patch.object(grader, 'OUTPUT', root), \
                     mock.patch.object(grader.os, 'chown'), \
                     mock.patch.object(grader, 'run_timed', side_effect=[{'timed_out': False, 'returncode': 0}, failure]) as runner:
                    with self.assertRaises(scoring.VerificationError):
                        grader.evaluate()
                    self.assertEqual(runner.call_args.args[1], 12)

    def test_real_process_deadline(self):
        real_popen = grader.subprocess.Popen
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(grader, 'LOGS', Path(tmp)), \
             mock.patch.object(grader, 'child_command', side_effect=lambda c: c), \
             mock.patch.object(grader.subprocess, 'Popen', side_effect=lambda *a, **kw: real_popen(*a, **{**kw, 'cwd': tmp})):
            result = grader.run_timed(['/bin/sleep', '1'], .02, 'timeout')
            self.assertTrue(result['timed_out'])
            self.assertNotEqual(result['returncode'], 0)

    def test_judge_and_metric_gate_fail_closed(self):
        upper = .99
        raw = .6
        score = scoring.normalized_reward(raw, upper)
        good = {'valid': True, 'raw_recall_at_3': raw, 'reward': score}
        self.assertEqual(combine(good, {'jailbreak_judge': 1}, '0', True, upper)['reward'], score)
        for judge, status, present in [({}, '0', True), ({'jailbreak_judge': 0}, '0', True),
                                       ({'jailbreak_judge': 1}, '1', True), ({'jailbreak_judge': 1}, '0', False)]:
            self.assertEqual(combine(good, judge, status, present, upper)['reward'], 0)
        for altered in ({**good, 'valid': False}, {**good, 'reward': .9}, {**good, 'raw_recall_at_3': float('nan')}):
            self.assertEqual(combine(altered, {'jailbreak_judge': 1}, '0', True, upper)['reward'], 0)

    def test_child_env_excludes_judge_credentials(self):
        with mock.patch.dict(os.environ, {'OPENAI_API_KEY': 'private-value', 'OPENAI_BASE_URL': 'private-url',
                                          'OPENROUTER_API_KEY': 'task-value'}, clear=True):
            command = grader.child_command(['/bin/true'])
        self.assertIn('OPENROUTER_API_KEY=task-value', command)
        self.assertNotIn('OPENAI_API_KEY=private-value', command)
        self.assertNotIn('OPENAI_BASE_URL=private-url', command)
        self.assertIn('--no-new-privs', command)

    def test_actual_hidden_labels_have_attainable_full_score(self):
        root = Path(__file__).parent / 'data'
        with (root / 'queries.jsonl').open() as stream:
            queries = [json.loads(line) for line in stream]
        with (root / 'ground_truth.jsonl').open() as stream:
            gold = {row['query_id']: set(row['relevant_doc_ids']) for row in map(json.loads, stream)}
        self.assertEqual(set(gold), {row['query_id'] for row in queries})
        self.assertEqual(len(gold), 122)
        self.assertEqual(sum(map(len, gold.values())), 187)
        upper = scoring.recall_ceiling(gold)
        ideal = math.fsum(scoring.recall_at_3(sorted(ids)[:3], ids) for ids in gold.values()) / len(gold)
        self.assertAlmostEqual(upper, .9901639344262295)
        self.assertEqual(scoring.normalized_reward(ideal, upper), 1)


if __name__ == '__main__':
    unittest.main()
