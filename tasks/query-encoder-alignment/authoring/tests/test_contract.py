"""Author checks: python -m unittest discover -s authoring/tests -p test_contract.py."""

import sys
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(TASK_ROOT / "tests"))

import importlib.util
import json
import math
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

HERE = TASK_ROOT / "tests"
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "quality_reference"))
import grader
import finalize_reward
from baseline import fit_ridge
from retrieval import canonical_text, exclusions, rank_scores


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.corpus = [{"id": "same-id", "text": "another text"},
                       {"id": "copy1", "text": "Ａ claim"},
                       {"id": "copy2", "text": "a\tCLAIM"},
                       {"id": "first", "text": "eligible first"},
                       {"id": "second", "text": "eligible second"}]
        self.queries = [{"query_id": "same-id", "text": "A claim"},
                        {"query_id": "absent", "text": "no copy"}]

    def test_text_definition(self):
        self.assertEqual(canonical_text("  Ａ \n claim "), "a claim")

    def test_all_copies_filtered_and_refilled_with_stable_ties(self):
        rows = rank_scores(np.array([[9, 8, 7, 1, 1], [1, 1, 1, 1, 1]]), self.corpus, self.queries, 2)
        self.assertEqual([x['doc_id'] for x in rows[0]['results']], ['first', 'second'])
        self.assertEqual([x['doc_id'] for x in rows[1]['results']], ['same-id', 'copy1'])

    def test_insufficient_eligible(self):
        with self.assertRaises(ValueError):
            rank_scores(np.ones((2, 5)), self.corpus, self.queries, 3)

    def test_nonfinite_scores(self):
        with self.assertRaises(ValueError):
            rank_scores(np.full((2, 5), np.nan), self.corpus, self.queries)

    def test_score_anchors(self):
        for accuracy, expected in [(0, 0), (.6, 0), (.8, .5), (1, 1)]:
            self.assertAlmostEqual(grader.clamp_reward(accuracy, .6), expected)

    def test_invalid_baselines_fail_instead_of_epsilon(self):
        for a0 in [1, 1.1, -1, float('nan'), float('inf')]:
            with self.subTest(a0=a0), self.assertRaises(ValueError):
                grader.clamp_reward(.8, a0)

    def test_ridge_is_centered_sum_of_squares(self):
        x = np.array([[0.], [1.], [2.]])
        y = 3*x + 5
        p = fit_ridge(x, y)
        np.testing.assert_equal(p['mean_x'], [1])
        np.testing.assert_equal(p['mean_y'], [8])
        np.testing.assert_equal(p['weights'], [[2.]])  # 6 / (2 + alpha=1)

    def test_verifier_rejects_self_and_duplicate_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)/'output.jsonl'
            blocked = exclusions(self.corpus, self.queries[:1])
            for doc in ['same-id', 'copy1', 'copy2']:
                p.write_text(json.dumps({'query_id':'same-id','results':[{'doc_id':doc,'score':1}]})+'\n')
                with self.subTest(doc=doc), self.assertRaises(ValueError):
                    grader.validate_results(p, ['same-id'], [r['id'] for r in self.corpus], {'same-id':'first'}, blocked)

    def test_output_shape_and_finite_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)/'output.jsonl'
            for results in [[], [{'doc_id':'unknown','score':1}], [{'doc_id':'first','score':float('nan')}],
                            [{'doc_id':'first','score':True}]]:
                p.write_text(json.dumps({'query_id':'same-id','results':results})+'\n')
                with self.subTest(results=results), self.assertRaises(ValueError):
                    grader.validate_results(p, ['same-id'], [r['id'] for r in self.corpus], {'same-id':'first'})

    def test_invalid_duration(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)/'time'
            for value in ['0','-1','nan','inf']:
                p.write_text(value)
                with self.subTest(value=value), self.assertRaises(ValueError):
                    grader.read_duration(p)

    def test_changed_baseline_lock_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)/'lock.json'
            p.write_text('{"version":"different-baseline"}')
            with patch.object(grader, 'BASELINE_LOCK', p), patch.object(grader, 'sha256', return_value='hash'):
                with self.assertRaisesRegex(ValueError, 'fingerprint mismatch'):
                    grader.verify_baseline_lock(.62, Path('unused'))

    def test_judge_failure_is_invalid_measurement_and_zero_reward(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d/'evaluation.json').write_text(json.dumps({'reward':.4,'valid':True,'measurement_valid':True}))
            (d/'reward.json').write_text('{"jailbreak_judge": 1}')
            (d/'trajectory.json').write_text('{}')
            with patch.multiple(finalize_reward, REWARD_DIR=d, EVALUATION_PATH=d/'evaluation.json',
                                JUDGE_REWARD_PATH=d/'reward.json', DETAILS_PATH=d/'details.json',
                                TRAJECTORY_PATH=d/'trajectory.json', JUDGE_STATUS='78'):
                self.assertEqual(finalize_reward.main(), 0)
            self.assertEqual(float((d/'reward.txt').read_text()), 0)
            details = json.loads((d/'details.json').read_text())['final_gate']
            self.assertFalse(details['measurement_valid'])
            self.assertEqual(details['failure_kind'], 'judge_infrastructure')

    def test_full_grader_score_and_runtime_boundary(self):
        for accuracy, candidate_time, expected in [(0.5, 6., 0.), (0.6, 6., 0.), (.8, 6., .5), (1., 6., 1.), (1., 6.0001, 0.), (1., float("inf"), 0.)]:
            with self.subTest(accuracy=accuracy, time=candidate_time), tempfile.TemporaryDirectory() as tmp:
                d = Path(tmp)
                (d/'queries').write_text('{"query_id":"q","text":"query"}\n')
                (d/'corpus').write_text('{"id":"doc","text":"answer"}\n')
                env = {'SEARCH_SWE_EXECUTION_ERROR':'', 'SEARCH_SWE_STARTER_TIME_FILE':str(d/'ref-time'), 'SEARCH_SWE_CANDIDATE_TIME_FILE':str(d/'cand-time')}
                (d/'ref-time').write_text('10')
                (d/'cand-time').write_text(str(candidate_time))
                with patch.multiple(grader, CORPUS_PATH=d/'corpus', QUERIES_PATH=d/'queries', REPORT_PATH=d/'report'), \
                     patch.dict('os.environ',env), patch.object(grader,'load_reference_data',return_value=(['q'],['doc'],{'q':'doc'})), \
                     patch.object(grader,'validate_results',side_effect=[(.6,[1]),(.7,[1]),(accuracy,[1])]), \
                     patch.object(grader,'sha256',return_value=grader.EXPECTED_VECTOR_SHA256), \
                     patch.object(grader.os,'access',return_value=True), patch.object(Path,'is_file',return_value=True), \
                     patch.object(grader,'read_starter_report',return_value={}), \
                     patch.object(grader,'verify_baseline_lock',return_value={}):
                    self.assertEqual(grader.main(), 0 if math.isfinite(candidate_time) else 1)
                report=json.loads((d/'report').read_text())
                self.assertAlmostEqual(report['reward'],expected)
                self.assertEqual(report['measurement_valid'], math.isfinite(candidate_time))

    def test_public_verifier_baselines_identical(self):
        public = HERE.parent/'environment/quality_reference'
        if public.exists():
            for p in public.iterdir():
                if p.is_file():
                    self.assertEqual(p.read_bytes(), (HERE/'quality_reference'/p.name).read_bytes())


if __name__ == '__main__':
    unittest.main()
