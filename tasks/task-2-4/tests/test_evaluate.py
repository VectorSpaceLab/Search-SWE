from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location("task2_4_evaluate", Path(__file__).with_name("evaluate.py"))
assert SPEC and SPEC.loader
EVALUATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(EVALUATE)


class EvaluateTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.write_jsonl("queries.jsonl", [
            {"query_id": "q1", "question": "First question"},
            {"query_id": "q2", "question": "Second question"},
        ])
        self.write_jsonl("corpus.jsonl", [{"docid": f"d{i}", "text": "Evidence"} for i in range(1, 11)])
        (self.root / "qrels.txt").write_text(
            "q1 0 d1 1\n" + "".join(f"q2 0 d{i} 1\n" for i in range(2, 7))
        )
        self.predictions = [
            {"query_id": "q1", "doc_ids": ["d1", "d7", "d8", "d9", "d10"]},
            {"query_id": "q2", "doc_ids": ["d2", "d3", "d7", "d8", "d9"]},
        ]

    def write_jsonl(self, name, records):
        (self.root / name).write_text("".join(json.dumps(row) + "\n" for row in records))

    def evaluate(self, predictions=None):
        self.write_jsonl("predictions.jsonl", self.predictions if predictions is None else predictions)
        argv = [
            "evaluate.py", "--queries", str(self.root / "queries.jsonl"),
            "--qrels", str(self.root / "qrels.txt"),
            "--corpus", str(self.root / "corpus.jsonl"),
            "--predictions", str(self.root / "predictions.jsonl"),
            "--report", str(self.root / "report.json"),
        ]
        with patch.dict(os.environ, {}, clear=True), patch.object(sys, "argv", argv), patch("builtins.print"):
            status = EVALUATE.main()
        return status, json.loads((self.root / "report.json").read_text())

    def assert_invalid(self, predictions, message):
        status, report = self.evaluate(predictions)
        self.assertEqual(status, 1)
        self.assertFalse(report["valid"])
        self.assertEqual(report["score"], 0.0)
        self.assertTrue(any(message in error for error in report["errors"]), report)

    def test_macro_recall_uses_gold_denominators_and_equal_query_weights(self):
        status, report = self.evaluate()
        self.assertEqual(status, 0)
        self.assertEqual(report["primary_metric"], {"name": "GoldRecall@5", "value": 0.7})
        self.assertEqual(report["score"], 70.0)
        self.assertEqual([row["gold_recall_at_5"] for row in report["per_query_metrics"]], [1.0, 0.4])

    def test_all_gold_documents_give_full_recall(self):
        self.predictions[1]["doc_ids"] = [f"d{i}" for i in range(2, 7)]
        status, report = self.evaluate()
        self.assertEqual(status, 0)
        self.assertEqual(report["primary_metric"]["value"], 1.0)

    def test_valid_misses_give_zero_recall(self):
        self.predictions[0]["doc_ids"] = ["d2", "d7", "d8", "d9", "d10"]
        self.predictions[1]["doc_ids"] = ["d1", "d7", "d8", "d9", "d10"]
        status, report = self.evaluate()
        self.assertEqual(status, 0)
        self.assertTrue(report["valid"])
        self.assertEqual(report["primary_metric"]["value"], 0.0)

    def test_order_within_five_does_not_change_recall(self):
        for row in self.predictions:
            row["doc_ids"].reverse()
        self.assertEqual(self.evaluate()[1]["primary_metric"]["value"], 0.7)

    def test_requires_exactly_five_string_ids(self):
        for value in ([], ["d1"] * 4, ["d1"] * 6, "d1,d2,d3,d4,d5", [1, "d2", "d3", "d4", "d5"], [[], "d2", "d3", "d4", "d5"]):
            with self.subTest(value=value):
                self.predictions[0]["doc_ids"] = value
                self.assert_invalid(self.predictions, "exactly 5 non-empty strings")

    def test_duplicate_document_ids_invalidate_entire_submission(self):
        self.predictions[0]["doc_ids"] = ["d1", "d1", "d7", "d8", "d9"]
        self.assert_invalid(self.predictions, "5 distinct document IDs")

    def test_unknown_corpus_document_invalidates_entire_submission(self):
        self.predictions[0]["doc_ids"][0] = "not-in-corpus"
        self.assert_invalid(self.predictions, "unknown corpus document IDs")

    def test_old_answer_only_output_is_invalid(self):
        self.predictions[0] = {"query_id": "q1", "answer": "An answer"}
        self.assert_invalid(self.predictions, "exactly 5 non-empty strings")

    def test_missing_duplicate_and_extra_query_outputs_are_invalid(self):
        for predictions, message in [
            (self.predictions[:1], "missing outputs"),
            (self.predictions + self.predictions[:1], "duplicate query_id"),
            (self.predictions + [{"query_id": "q3", "doc_ids": ["d1", "d2", "d3", "d4", "d5"]}], "unknown query_id"),
        ]:
            with self.subTest(message=message):
                self.assert_invalid(predictions, message)

    def test_query_id_must_be_a_string(self):
        self.predictions[0]["query_id"] = ["q1"]
        self.assert_invalid(self.predictions, "unknown query_id")

    def test_malformed_json_and_non_object_results_are_rejected(self):
        path = self.root / "broken.jsonl"
        path.write_text('not-json\n[]\n')
        _, errors = EVALUATE.load_predictions(path, {"q1"})
        self.assertTrue(any("invalid JSON" in error for error in errors))
        self.assertTrue(any("result must be an object" in error for error in errors))

    def test_missing_prediction_file_is_invalid(self):
        _, errors = EVALUATE.load_predictions(self.root / "missing.jsonl", {"q1"})
        self.assertTrue(any("cannot open predictions" in error for error in errors))

    def test_invalid_gold_inputs_fail_closed(self):
        for labels, message in [
            ("q1 0 d1 1\n", "IDs do not match"),
            ("q1 0 d1 1\nq1 0 d1 1\n", "duplicate gold"),
            ("".join(f"q1 0 d{i} 1\n" for i in range(1, 7)), "1-5 gold documents"),
            ("q1 0 absent 1\nq2 Q0 d2 1\n", "outside the corpus"),
        ]:
            with self.subTest(message=message):
                (self.root / "qrels.txt").write_text(labels)
                status, report = self.evaluate()
                self.assertEqual(status, 2)
                self.assertFalse(report["valid"])
                self.assertTrue(any(message in error for error in report["errors"]), report)


if __name__ == "__main__":
    unittest.main()
