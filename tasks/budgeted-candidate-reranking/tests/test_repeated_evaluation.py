"""Repeated evaluation uses one deployment and five independent query invocations."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent/'runtime'))
import evaluate as engine


class RepeatedEvaluation(unittest.TestCase):
    def fixture(self, times, fail=False):
        root = tempfile.TemporaryDirectory()
        self.addCleanup(root.cleanup)
        directory = Path(root.name)
        queries = directory/'queries.jsonl'
        queries.write_text(''.join(json.dumps({'query_id': q, 'candidates': [{'doc_id': 'a'}]})+'\n' for q in ['q1','q2']))
        qrels = directory/'qrels.json'
        qrels.write_text(json.dumps({'q1': {'a': 1}, 'q2': {'a': 1}}))
        backend = MagicMock(broken=False, info={'fixture': True})
        backend.request.return_value = {}
        resources = MagicMock()
        resources.report.return_value = {'fixture': True}
        seen = []
        def query_run(query, submission, runtime, output, tracker):
            repeat = len(seen)//2
            seen.append((query['query_id'], output))
            valid = not (fail and query['query_id']=='q2' and repeat==0)
            return {'query_id': query['query_id'], 'status': 'ok' if valid else 'failed',
                    'ids': ['a'] if valid else [], 'local_seconds': times[repeat],
                    'inference_seconds': .1, 'spent_tokens': 64,
                    'calls': [{'input_tokens': 64, 'output_tokens': 0}]}
        with patch.object(engine.isolation, 'protect'), patch.object(engine.isolation, 'cleanup'), \
             patch.object(engine, 'freeze_submission'), patch.object(engine, 'verify_model'), \
             patch.object(engine, 'Resources', return_value=resources), \
             patch.object(engine, 'Backend', return_value=backend) as deployment, \
             patch.object(engine, 'run_query', side_effect=query_run):
            report = engine.evaluate(directory/'submission', queries, qrels, directory/'output')
        self.assertEqual(deployment.call_count, 1)
        self.assertEqual(backend.request.call_count, 1)
        self.assertEqual(len(seen), 10)
        self.assertEqual(len({row[1] for row in seen}), 5)
        self.assertEqual(report['token_usage']['weighted_tokens_total'], 640)
        self.assertEqual(report['token_usage']['max_weighted_tokens_per_query'], 64)
        return report

    def test_two_slow_samples_still_meet_the_median_limit(self):
        report = self.fixture([.5, .5, .5, 1.5, 1.5])
        self.assertEqual(report['quality'], 1)
        self.assertTrue(all(len(q['measurements'])==5 for q in report['queries']))

    def test_three_slow_samples_fail_the_median_limit(self):
        report = self.fixture([.5, .5, 1.5, 1.5, 1.5])
        self.assertEqual(report['quality'], 0)

    def test_invalid_result_is_not_dropped_from_the_average(self):
        report = self.fixture([.5]*5, fail=True)
        self.assertEqual(report['quality'], .5)
        self.assertEqual(report['queries'][1]['status'], 'failed')
