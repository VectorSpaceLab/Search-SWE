"""Fast metric/accounting tests; isolated process tests require a disposable container."""
import gzip
import json
import math
import os
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT/'runtime'))
from metrics import ndcg, validate_result
from model import Meter, FixedModel, deployment_config


class MetricTests(unittest.TestCase):
    def test_linear_gain_and_complete_ideal(self):
        expected = 1/(3+1/math.log2(3))
        self.assertAlmostEqual(ndcg(['b'], {'a': 3, 'b': 1}), expected)
        self.assertEqual(ndcg([], {'a': 3}), 0)
        self.assertEqual(ndcg(['unjudged'], {'a': 3}), 0)
        self.assertEqual(ndcg(['a'], {}), 0)

    def test_oracle_and_wrong_order(self):
        self.assertEqual(ndcg(['a', 'b'], {'a': 3, 'b': 1}), 1)
        self.assertLess(ndcg(['b', 'a'], {'a': 3, 'b': 1}), 1)

    def test_output_validation(self):
        q = {'candidates': [{'doc_id': str(i)} for i in range(100)]}
        self.assertEqual(validate_result({'type': 'result', 'ids': []}, q), [])
        self.assertEqual(validate_result({'type': 'result', 'ids': ['99']}, q), ['99'])
        for message in ({'type': 'result', 'ids': ['0', '0']},
                        {'type': 'result', 'ids': ['outside']},
                        {'type': 'result', 'ids': [0]},
                        {'type': 'result', 'ids': [str(i) for i in range(11)]},
                        {'type': 'result', 'ids': [], 'score': 1},
                        {'type': 'result', 'ids': '0'}):
            with self.subTest(message=message), self.assertRaises(ValueError):
                validate_result(message, q)


class AccountingTests(unittest.TestCase):
    def test_exact_boundary_reserve_settle(self):
        m = Meter(100)
        r = m.reserve(60, 10)
        self.assertEqual(m.spent, 100)
        with self.assertRaises(ValueError):
            m.reserve(1, 1)
        m.settle(r, 2)
        self.assertEqual(m.spent, 68)
        with self.assertRaises(RuntimeError):
            m.settle(r, 0)
        self.assertEqual(m.reserve(28, 1)['charged_tokens'], 32)

    def test_failed_request_stays_charged_and_connections_share_state(self):
        m = Meter(100)
        m.reserve(80, 5)
        # A second client gets the same authoritative query object, not new credit.
        client2 = m
        with self.assertRaises(ValueError):
            client2.reserve(1, 1)
        self.assertEqual(client2.spent, 100)

    def test_new_query_does_not_borrow_unused_budget(self):
        first, second = Meter(100), Meter(100)
        first.reserve(10, 1)
        with self.assertRaises(ValueError):
            second.reserve(100, 1)

    def test_client_cannot_supply_budget_state_or_custom_model(self):
        model = object.__new__(FixedModel)
        for extra in ({'spent_tokens': 0}, {'budget': 100000}, {'model': '/app/custom'},
                      {'reset': True}, {'tokenizer': 'custom'}):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                model.prepare({'type': 'generate', 'messages': [{'role': 'user', 'content': 'test'}],
                               'max_new_tokens': 1, **extra}, set())

    def test_only_supported_deployment_fields(self):
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'deployment.json'
            path.write_text('{}')
            self.assertEqual(deployment_config(path), {'attention': 'sdpa', 'cpu_threads': 8})
            for config in ({'cpu_threads': True}, {'cpu_threads': 17},
                           {'attention': 'custom'}, {'callback': '/app/code.py'}, []):
                path.write_text(json.dumps(config))
                with self.assertRaises(ValueError):
                    deployment_config(path)


class AssetTests(unittest.TestCase):
    def test_all_test_queries_and_candidates_are_retained(self):
        with gzip.open(ROOT/'data/hidden.jsonl.gz', 'rt') as f:
            rows = [json.loads(line) for line in f]
        judgments = json.loads((ROOT/'data/hidden-qrels.json').read_text())
        self.assertEqual(len(rows), 54)
        self.assertEqual({q['query_id'] for q in rows}, set(judgments))
        for q in rows:
            self.assertEqual(len(q['candidates']), 100)
            self.assertEqual(len({d['doc_id'] for d in q['candidates']}), 100)
            self.assertEqual([d['rank'] for d in q['candidates']], list(range(1,101)))
            self.assertTrue(all(math.isfinite(d['bm25_score']) for d in q['candidates']))
            self.assertTrue(all(0 <= g <= 3 for g in judgments[q['query_id']].values()))

    def test_trusted_runtime_copies_are_identical(self):
        original = ROOT.parent/'environment/runtime'
        if not original.exists():
            self.skipTest('Source copy comparison is a repository-local check')
        for p in original.iterdir():
            if p.is_file():
                self.assertEqual(p.read_bytes(), (ROOT/'runtime'/p.name).read_bytes(), p.name)


if __name__ == '__main__':
    unittest.main()
