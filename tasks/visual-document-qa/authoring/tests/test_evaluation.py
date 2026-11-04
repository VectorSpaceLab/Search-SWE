
import sys
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(TASK_ROOT / "tests"))

import unittest
from evaluation import validate, aggregate
from upstream_metrics import rule_based_eval_score_mmlongbenchdoc as score


class Cases(unittest.TestCase):
    def test_exact(self):
        self.assertEqual(score("GPT-4", "GPT-4", "Str"), 1)

    def test_wrong_number(self):
        self.assertEqual(score("12", "19", "Int"), 0)

    def test_float(self):
        self.assertEqual(score("21%", "21%", "Float"), 1)

    def test_list_order(self):
        self.assertEqual(score("['A','B']", "['B','A']", "List"), 1)

    def test_missing_list_item(self):
        self.assertEqual(score("['A','B']", "['A']", "List"), 0)

    def test_unanswerable(self):
        self.assertEqual(score("Not answerable", "Not answerable", "None"), 1)

    def test_wrong_unanswerable(self):
        self.assertEqual(score("Not answerable", "23", "None"), 0)

    def test_output(self):
        q = {"query_id": "x", "doc_id": "d"}
        docs = {"d": {"page_count": 10}}
        self.assertEqual(
            validate(q, {"query_id": "x", "answer": "yes", "pages": [2]}, docs),
            ("yes", [2]),
        )
        for pages in [[True], [0], [11], [2, 2]]:
            with self.assertRaises(ValueError):
                validate(q, {"query_id": "x", "answer": "yes", "pages": pages}, docs)

    def test_macro(self):
        v, parts = aggregate(
            [
                {"branch": "A", "value": 1},
                {"branch": "A", "value": 0},
                {"branch": "B", "value": 1},
            ]
        )
        self.assertEqual(v, 0.75)


if __name__ == "__main__":
    unittest.main()
