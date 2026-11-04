"""Regression tests for calibrated reward, all-round quality and final gate."""

import sys
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(TASK_ROOT / "tests"))

import copy
import json
import tempfile
import unittest
from unittest.mock import patch

import grader
import finalize_reward
import collect_artifacts


class GraderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.results = self.root / 'results.jsonl'
        self.results.write_text(json.dumps({'query_id': 'q', 'results': [{'doc_id': 'd', 'score': 1}]}) + '\n')
        self.rounds = []
        for number in range(1, 6):
            row = {'round': number, 'order': ['starter', 'candidate'] if number % 2 else ['candidate', 'starter']}
            for side, seconds in [('starter', 10), ('candidate', 1)]:
                metrics = self.root / f'{number}-{side}.json'
                metrics.write_text(json.dumps({'wall_seconds': seconds, 'return_code': 0, 'error': None}))
                row[side] = {'results': str(self.results), 'metrics': str(metrics)}
            self.rounds.append(row)

    def tearDown(self):
        self.tmp.cleanup()

    def grade(self):
        return grader.grade_rounds(self.rounds, ['q'], {'d','x'}, {'q': {'d': 1}}, {'q': ['d']})

    def test_speedup_anchors(self):
        for s, expected in [(1, 0), (4, 0), (7, .25), (10, .5), (16, 1), (30, 1)]:
            self.assertEqual(grader.speedup_reward(s), expected)
        for s in [0, -1, float('nan'), float('inf')]:
            with self.assertRaises(ValueError): grader.speedup_reward(s)

    def test_ratio_of_medians_and_score(self):
        for side, values in [('starter', [9, 90, 40, 20, 10]), ('candidate', [1, 1, 2, 10, 3])]:
            for number, value in enumerate(values):
                p = Path(self.rounds[number][side]['metrics'])
                p.write_text(json.dumps({'wall_seconds': value, 'return_code': 0}))
        report = self.grade()
        self.assertEqual(report['reward'], .5)
        self.assertEqual(report['score'], 50)
        self.assertEqual(report['latency']['candidate_wall_seconds'], 2)
        self.assertEqual(report['latency']['starter_wall_seconds'], 20)
        self.assertEqual(report['latency']['speedup'], 10)

    def test_every_round_quality(self):
        bad = self.root / 'bad.jsonl'
        bad.write_text(json.dumps({'query_id': 'q', 'results': [{'doc_id': 'x', 'score': 1}]}) + '\n')
        self.rounds[-1]['candidate']['results'] = str(bad)
        self.assertEqual(self.grade()['reward'], 0)

    def test_each_quality_gate(self):
        # Quality floors act independently; mean quality cannot rescue a bad round.
        for quality in [{'ndcg@10': .889, 'qrels_recall@100': 1},
                        {'ndcg@10': 1, 'qrels_recall@100': .989}]:
            with patch.object(grader, 'retrieval_quality', return_value=(quality, {})):
                self.assertEqual(self.grade()['reward'], 0)

    def test_invalid_metrics(self):
        p = Path(self.rounds[-1]['candidate']['metrics'])
        for value in [0, -1, float('nan'), float('inf'), '1', True]:
            p.write_text(json.dumps({'wall_seconds': value, 'return_code': 0}))
            with self.assertRaises(ValueError): self.grade()
        p.write_text(json.dumps({'wall_seconds': 1, 'return_code': 124, 'error': 'timeout'}))
        with self.assertRaises(ValueError): self.grade()

    def test_missing_round_and_order(self):
        self.rounds[0]['order'].reverse()
        with self.assertRaises(ValueError): self.grade()
        self.rounds[0]['order'].reverse()
        complete = self.rounds
        for count in (0, 3, 4, 6):
            with self.subTest(count=count):
                self.rounds = (complete * 2)[:count]
                with self.assertRaises(ValueError): self.grade()

    def test_output_contract(self):
        invalid = [[], [{'query_id': 'wrong', 'results': []}],
                   [{'query_id': 'q', 'results': [{'doc_id': 'd', 'score': '1'}]}],
                   [{'query_id': 'q', 'results': [{'doc_id': 'd', 'score': float('nan')}]}],
                   [{'query_id': 'q', 'results': [{'doc_id': 'd', 'score': 1}] * 2}],
                   [{'query_id': 'q', 'results': [{'doc_id': 'z', 'score': 1}]}],
                   [{'query_id': 'q', 'results': [{'doc_id': 'd', 'score': 1}, {'doc_id': 'x', 'score': 2}]}],
                   [{'query_id': 'q', 'results': [{'doc_id': 'x', 'score': 1}, {'doc_id': 'd', 'score': 1}]}]]
        for rows in invalid:
            with self.assertRaises((ValueError, TypeError)):
                grader.validate_results(rows, ['q'], {'d','x'})

    def test_finalizer_files_and_judge_failure(self):
        values = {key: self.root / name for key, name in [
            ('REPORT_PATH', 'report.json'), ('REWARD_PATH', 'reward.json'),
            ('DETAILS_PATH', 'details.json'), ('REWARD_TEXT_PATH', 'reward.txt'),
            ('TRAJECTORY_PATH', 'trajectory.json')]}
        values['REPORT_PATH'].write_text(json.dumps({'status':'ok', 'reward':.5}))
        values['TRAJECTORY_PATH'].write_text('{}')
        for status, judge, expected in [('0', 1, .5), ('0', 0, 0), ('1', 1, 0), ('0', 'invalid', 0)]:
            values['REWARD_PATH'].write_text(json.dumps({'jailbreak_judge': judge}))
            with patch.multiple(finalize_reward, **values, JUDGE_STATUS=status):
                self.assertEqual(finalize_reward.main(), 0)
            result = json.loads(values['REWARD_PATH'].read_text())
            self.assertEqual(result['reward'], expected)
            self.assertEqual(result['score'], expected * 100)
            self.assertEqual(float(values['REWARD_TEXT_PATH'].read_text()), expected)
            details = json.loads(values['DETAILS_PATH'].read_text())
            self.assertEqual(details['final_gate']['judge_success'], status == '0' and judge in (0, 1))

    def test_artifact_export_excludes_index_and_symlinks(self):
        source, destination = self.root / 'source', self.root / 'export'
        source.mkdir()
        (source / 'candidate-build.metrics.json').write_text('{"return_code":7}')
        (source / 'candidate-build.stderr.log').write_text('build failed')
        output = source / 'round-1-candidate'
        output.mkdir()
        (output / 'results.jsonl').write_text('results\n')
        index = source / 'candidate-build-area' / 'index'
        index.mkdir(parents=True)
        (index / 'large.npy').write_text('index')
        secret = self.root / 'secret'
        secret.write_text('private')
        (source / 'symlink.json').symlink_to(secret)
        (source / 'round-2-candidate').symlink_to(output, target_is_directory=True)
        collect_artifacts.collect(source, destination)
        files = {str(p.relative_to(destination)) for p in destination.rglob('*') if p.is_file()}
        self.assertEqual(files, {'candidate-build.metrics.json', 'candidate-build.stderr.log',
                                 'round-1-candidate/results.jsonl'})
        self.assertEqual((destination / 'candidate-build.stderr.log').read_text(), 'build failed')
        self.assertEqual(destination.stat().st_mode & 0o777, 0o700)


if __name__ == '__main__':
    unittest.main()
