
import sys
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(TASK_ROOT / "tests"))

import unittest, math
from evaluation import ndcg, validate, aggregate


class Tests(unittest.TestCase):
    def setUp(self):
        self.q = {"query_id": "q", "domain": "collection-01"}
        self.pages = {"a": "collection-01", "b": "collection-01", "x": "collection-02"}

    def test_ideal(self):
        self.assertEqual(ndcg(["a", "b"], {"a": 1, "b": 1}), 1)

    def test_rank_loss(self):
        self.assertAlmostEqual(ndcg(["x", "a"], {"a": 1}), 1 / math.log2(3))

    def test_valid(self):
        self.assertEqual(
            validate(
                self.q,
                {"query_id": "q", "results": [{"doc_id": "a", "score": 1}]},
                self.pages,
            ),
            ["a"],
        )

    def test_wrong_domain(self):
        with self.assertRaises(ValueError):
            validate(
                self.q,
                {"query_id": "q", "results": [{"doc_id": "x", "score": 1}]},
                self.pages,
            )

    def test_duplicate(self):
        with self.assertRaises(ValueError):
            validate(
                self.q,
                {"query_id": "q", "results": [{"doc_id": "a", "score": 1}] * 2},
                self.pages,
            )

    def test_nan(self):
        with self.assertRaises(ValueError):
            validate(
                self.q,
                {"query_id": "q", "results": [{"doc_id": "a", "score": float("nan")}]},
                self.pages,
            )

    def test_macro(self):
        self.assertEqual(
            aggregate(
                [{"domain": "a", "value": 1}] * 3 + [{"domain": "b", "value": 0}]
            )[0],
            0.5,
        )
