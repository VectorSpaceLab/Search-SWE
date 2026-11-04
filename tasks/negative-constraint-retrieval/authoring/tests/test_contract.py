"""Author-side, credential-free checks of public scoring and failure behavior."""

import sys
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(TASK_ROOT / "tests"))

import json
import tempfile
import unittest
from unittest.mock import patch
import grader
import finalize_reward

class OutputContract(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'results.jsonl'
        self.patch=patch.object(grader,'OUTPUT_PATH',self.path); self.patch.start();self.addCleanup(self.patch.stop)
        self.queries=[{'query_id':'a','text':'A'},{'query_id':'b','text':'B'}]
        self.rows=[{'query_id':q['query_id'],'results':[{'doc_id':'d1','score':.2}]} for q in self.queries]

    def validate(self,rows):
        self.path.write_text(''.join(json.dumps(r)+'\n' for r in rows))
        return grader.validate_output(self.queries,{'d1','d2'},{'d1':0,'d2':1})

    def test_valid_output_reordered(self):
        result=self.validate(self.rows[::-1])
        self.assertEqual([r['query_id'] for r in result],['a','b'])

    def test_reject_coverage_errors(self):
        for rows in [self.rows[:1],self.rows+[self.rows[0]],[self.rows[0],self.rows[0]]]:
            with self.subTest(rows=rows), self.assertRaises(grader.VerificationError):self.validate(rows)

    def test_reject_invalid_items(self):
        for value in [[],[{'doc_id':'d1','score':True}],[{'doc_id':'d1','score':float('nan')}],
                      [{'doc_id':'missing','score':1}],[{'doc_id':'d1','score':'1'}],
                      [{'doc_id':'d1','score':1}]*2,[{'doc_id':1,'score':1}]]:
            with self.subTest(value=value),self.assertRaises(grader.VerificationError):
                self.validate([self.rows[0],{'query_id':'b','results':value}])

    def test_reject_missing_output(self):
        with self.assertRaises(grader.VerificationError):
            grader.validate_output(self.queries,{'d1'},{'d1':0})

    def test_accept_symlink_output(self):
        self.path.symlink_to(self.path.parent/'target')
        result=self.validate(self.rows)
        self.assertEqual([r['query_id'] for r in result],['a','b'])

    def test_accept_output_larger_than_former_limit(self):
        self.path.write_text(' '*(4*1024*1024)+''.join(json.dumps(r)+'\n' for r in self.rows))
        result=grader.validate_output(self.queries,{'d1'},{'d1':0})
        self.assertEqual([r['query_id'] for r in result],['a','b'])

    def test_reject_malformed_output(self):
        self.path.write_text('{oops}\n')
        with self.assertRaises(grader.VerificationError):
            grader.validate_output(self.queries,{'d1'},{'d1':0})

class RewardGate(unittest.TestCase):
    def test_fractional_reward_and_fail_closed_audit(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);evaluation=root/'evaluation.json';reward=root/'reward.json';trajectory=root/'trajectory.json'
            evaluation.write_text(json.dumps({'valid':True,'primary_metric':{'value':.9}}))
            trajectory.write_text('{}')
            with patch.multiple(finalize_reward,REWARD_DIR=root,EVALUATION_PATH=evaluation,
                                JUDGE_REWARD_PATH=reward,DETAILS_PATH=root/'details.json',TRAJECTORY_PATH=trajectory):
                for status,judge,expected in [('0',1,.9),('78',1,0),('0',0,0),('0',None,0)]:
                    reward.write_text(json.dumps({'jailbreak_judge':judge}))
                    with patch.object(finalize_reward,'JUDGE_STATUS',status):finalize_reward.main()
                    self.assertEqual(json.loads(reward.read_text())['reward'],expected)
                    self.assertEqual(float((root/'reward.txt').read_text()),expected)
                trajectory.unlink();reward.write_text('{"jailbreak_judge":1}')
                with patch.object(finalize_reward,'JUDGE_STATUS','0'):finalize_reward.main()
                self.assertEqual(json.loads(reward.read_text())['reward'],0)

class QueryDeadlines(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.root = root
        self.output = root / 'results.jsonl'
        self.input = root / 'queries.jsonl'
        self.queries = [{'query_id': 'a', 'text': 'A'}, {'query_id': 'b', 'text': 'B'}]
        patches = patch.multiple(grader, OUTPUT_PATH=self.output, OUTPUT_DIR=root, RESULTS_DIR=root)
        patches.start()
        self.addCleanup(patches.stop)

    def stage(self, rows, *, filename):
        self.assertEqual(len(rows), 1)
        self.input = self.root / ('input-' + filename)
        self.input.write_text(json.dumps(rows[0]) + '\n')
        return self.input

    def successful_run(self, command, **kwargs):
        self.assertEqual(kwargs['timeout'], 8.0)
        self.output = Path(command[command.index('--output') + 1])
        self.assertFalse(self.output.exists())
        row = json.loads(Path(command[command.index('--queries') + 1]).read_text())
        self.output.write_text(json.dumps({'query_id': row['query_id'],
            'results': [{'doc_id': 'd1', 'score': 1.0}]}) + '\n')
        return {'returncode': 0, 'elapsed_seconds': .1, 'timed_out': False}

    def test_one_query_at_a_time_with_independent_deadlines(self):
        metrics = {}
        with patch.object(grader, 'stage_queries', side_effect=self.stage) as stage, \
             patch.object(grader, 'run_timed', side_effect=self.successful_run) as run:
            results = grader.run_queries(self.queries, {'d1'}, {'d1': 0}, metrics)
        self.assertEqual([row['query_id'] for row in results], ['a', 'b'])
        self.assertEqual(stage.call_count, 2)
        self.assertEqual(run.call_count, 2)
        self.assertEqual(metrics['elapsed_seconds'], .2)
        self.assertEqual(metrics['per_query_timeout_seconds'], 8)
        self.assertEqual(len({c.kwargs['filename'] for c in stage.call_args_list}), 2)
        self.assertEqual(len({c.args[0][c.args[0].index('--output') + 1] for c in run.call_args_list}), 2)

    def test_timeout_cannot_use_time_saved_by_previous_query(self):
        metrics = {}
        calls = 0
        def run(command, **kwargs):
            nonlocal calls
            calls += 1
            if calls != 2:
                return self.successful_run(command, **kwargs)
            # Even a correct output is worth zero if the command times out.
            self.successful_run(command, **kwargs)
            return {'returncode': -9, 'elapsed_seconds': 8.2, 'timed_out': True}
        with patch.object(grader, 'stage_queries', side_effect=self.stage), \
             patch.object(grader, 'run_timed', side_effect=run):
            results = grader.run_queries(self.queries + [{'query_id': 'c', 'text': 'C'}], {'d1'}, {'d1': 0}, metrics)
        self.assertEqual(calls, 3)
        self.assertEqual([r['results'] for r in results], [['d1'], [], ['d1']])
        self.assertTrue(results[1]['timed_out'])
        self.assertTrue(metrics['timed_out'])
        self.assertEqual(metrics['queries'][-1]['query_id'], 'c')
        self.assertEqual(metrics['returncode'], -9)

    def test_all_timeouts_still_cover_every_query(self):
        metrics = {}
        with patch.object(grader, 'stage_queries', side_effect=self.stage), \
             patch.object(grader, 'run_timed', return_value={
                 'returncode': -9, 'elapsed_seconds': 8.2, 'timed_out': True}):
            results = grader.run_queries(self.queries, {'d1'}, {'d1': 0}, metrics)
        self.assertEqual(len(results), 2)
        self.assertTrue(all(r['timed_out'] and not r['results'] for r in results))

    def test_timeout_is_in_full_denominator_and_survives_reward_gate(self):
        queries = self.queries + [{'query_id': 'c', 'text': 'C'}]
        calls = 0
        def run(command, **kwargs):
            nonlocal calls
            if command[0].endswith('build.sh'):
                return {'returncode': 0, 'elapsed_seconds': .1, 'timed_out': False}
            calls += 1
            if calls == 2:
                return {'returncode': -9, 'elapsed_seconds': 8.2, 'timed_out': True}
            return self.successful_run(command, **kwargs)
        report_path = self.root / 'evaluation.json'
        with patch.multiple(grader, REPORT_PATH=report_path, EXECUTION_ERROR=''), \
             patch.object(grader, 'recreate_workdirs'), \
             patch.object(grader, 'load_corpus', return_value=({'d1'}, {'d1': 0})), \
             patch.object(grader, 'load_private_data', return_value=(queries, {q['query_id']: {'d1'} for q in queries})), \
             patch.object(grader, 'check_submission_boundary'), \
             patch.object(grader, 'stage_queries', side_effect=self.stage), \
             patch.object(grader, 'stop_submission_processes'), \
             patch.object(grader, 'run_timed', side_effect=run):
            self.assertEqual(grader.main(), 0)
        report = json.loads(report_path.read_text())
        self.assertTrue(report['valid'])
        self.assertEqual(report['errors'], [])
        self.assertEqual(report['query_count'], 3)
        self.assertEqual(report['passed_queries'], 2)
        self.assertEqual(report['timed_out_queries'], 1)
        self.assertEqual(report['reward'], 2 / 3)
        reward = self.root / 'reward.json'
        reward.write_text('{"jailbreak_judge": 1}')
        trajectory = self.root / 'trajectory.json'
        trajectory.write_text('{}')
        with patch.multiple(finalize_reward, REWARD_DIR=self.root, EVALUATION_PATH=report_path,
                            JUDGE_REWARD_PATH=reward, DETAILS_PATH=self.root / 'details.json',
                            TRAJECTORY_PATH=trajectory, JUDGE_STATUS='0'):
            finalize_reward.main()
        self.assertAlmostEqual(json.loads(reward.read_text())['reward'], 2 / 3)

    def test_non_timeout_command_failure_still_rejected(self):
        with patch.object(grader, 'stage_queries', side_effect=self.stage), \
             patch.object(grader, 'run_timed', return_value={
                 'returncode': 7, 'elapsed_seconds': .1, 'timed_out': False}), \
             self.assertRaisesRegex(grader.VerificationError, 'exited with 7'):
            grader.run_queries(self.queries, {'d1'}, {'d1': 0}, {})

    def test_missing_second_output_cannot_reuse_first(self):
        metrics = {}
        calls = 0
        def run(command, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                return self.successful_run(command, **kwargs)
            return {'returncode': 0, 'elapsed_seconds': .1, 'timed_out': False}
        with patch.object(grader, 'stage_queries', side_effect=self.stage), \
             patch.object(grader, 'run_timed', side_effect=run), \
             self.assertRaisesRegex(grader.VerificationError, 'cannot read'):
            grader.run_queries(self.queries, {'d1'}, {'d1': 0}, metrics)

if __name__=='__main__':unittest.main()
