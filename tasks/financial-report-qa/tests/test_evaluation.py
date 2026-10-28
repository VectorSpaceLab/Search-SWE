import json, tempfile, unittest
from pathlib import Path
from evaluation import validate_prediction, evidence_recall, evaluate_rows
from batch_runtime import completed_rows


class EvidenceScoring(unittest.TestCase):
    def setUp(self):
        self.q = {"query_id": "q", "question": "Find both supporting facts."}
        self.docs = {"report-a": "x" * 1000, "report-b": "x" * 1000}
        self.gold = {
            "query_id": "q",
            "evidence": [
                {
                    "evidence_id": "e1",
                    "locations": [{"document_id": "report-a", "start": 10, "end": 20}],
                },
                {
                    "evidence_id": "e2",
                    "locations": [{"document_id": "report-a", "start": 40, "end": 50}],
                },
            ],
        }

    def span(self, a, b, did="report-a"):
        return {"document_id": did, "start": a, "end": b}

    def result(self, spans):
        return {"query_id": "q", "spans": spans}

    def test_all_facts_in_one_span(self):
        self.assertEqual(evidence_recall(self.gold, [self.span(5, 55)])[0], 1)

    def test_partial_recall(self):
        self.assertEqual(evidence_recall(self.gold, [self.span(10, 20)])[0], 0.5)

    def test_wrong_report_never_hits(self):
        self.assertEqual(
            evidence_recall(self.gold, [self.span(5, 55, "report-b")])[0], 0
        )

    def test_wrong_location_never_hits(self):
        self.assertEqual(evidence_recall(self.gold, [self.span(200, 300)])[0], 0)

    def test_one_character_overlap_does_not_cover_fact(self):
        self.assertEqual(evidence_recall(self.gold, [self.span(19, 25)])[0], 0)

    def test_duplicate_hits_count_once(self):
        self.assertEqual(evidence_recall(self.gold, [self.span(10, 20)] * 5)[0], 0.5)

    def test_contiguous_spans_can_cover_one_fact(self):
        self.assertEqual(
            evidence_recall(self.gold, [self.span(10, 15), self.span(15, 20)])[0], 0.5
        )

    def test_gap_does_not_cover_fact(self):
        self.assertEqual(
            evidence_recall(self.gold, [self.span(10, 14), self.span(15, 20)])[0], 0
        )

    def test_alternative_locations_are_one_fact(self):
        self.gold["evidence"][0]["locations"].append(self.span(100, 110, "report-b"))
        self.assertEqual(
            evidence_recall(
                self.gold, [self.span(10, 20), self.span(100, 110, "report-b")]
            )[0],
            0.5,
        )

    def test_empty_is_valid_zero(self):
        self.assertEqual(validate_prediction(self.q, self.result([]), self.docs), [])
        self.assertEqual(evidence_recall(self.gold, [])[0], 0)

    def test_unicode_characters_not_bytes(self):
        docs = {"emoji": "😀" * 512}
        self.assertEqual(
            len(
                validate_prediction(
                    self.q, self.result([self.span(0, 512, "emoji")]), docs
                )
            ),
            1,
        )

    def test_invalid_ranges(self):
        for span in [
            self.span(0, 513),
            self.span(-1, 2),
            self.span(2, 2),
            self.span(999, 1001),
            self.span(True, 2),
            self.span(0, 1, "missing"),
        ]:
            with self.subTest(span=span), self.assertRaises(ValueError):
                validate_prediction(self.q, self.result([span]), self.docs)

    def test_six_results_invalid(self):
        with self.assertRaises(ValueError):
            validate_prediction(self.q, self.result([self.span(10, 20)] * 6), self.docs)

    def test_answer_or_target_fields_are_not_the_interface(self):
        for prediction in [
            {"query_id": "q", "answer": "100"},
            dict(self.result([]), document_id="report-a"),
        ]:
            with self.assertRaises(ValueError):
                validate_prediction(self.q, prediction, self.docs)

    def test_query_mean_not_fact_weighted(self):
        q2 = dict(self.q, query_id="q2")
        gold2 = {"query_id": "q2", "evidence": [self.gold["evidence"][0]]}
        predictions = [
            self.result([self.span(10, 20)]),
            {"query_id": "q2", "spans": [self.span(10, 20)]},
        ]
        value, _ = evaluate_rows(
            [self.q, q2], predictions, {"q": self.gold, "q2": gold2}, self.docs
        )
        self.assertEqual(value, 0.75)

    def test_missing_or_duplicate_rows_zero_only_that_query(self):
        q2 = dict(self.q, query_id="q2")
        gold2 = dict(self.gold, query_id="q2")
        for predictions in [
            [self.result([self.span(5, 55)])],
            [
                self.result([self.span(5, 55)]),
                {"query_id": "q2", "spans": []},
                {"query_id": "q2", "spans": []},
            ],
        ]:
            value, _ = evaluate_rows(
                [self.q, q2], predictions, {"q": self.gold, "q2": gold2}, self.docs
            )
            self.assertEqual(value, 0.5)

    def test_malformed_range_zero_only_that_query(self):
        q2 = dict(self.q, query_id="q2")
        gold2 = dict(self.gold, query_id="q2")
        predictions = [
            self.result([self.span(5, 55)]),
            {"query_id": "q2", "spans": [self.span(0, 513)]},
        ]
        self.assertEqual(
            evaluate_rows(
                [self.q, q2], predictions, {"q": self.gold, "q2": gold2}, self.docs
            )[0],
            0.5,
        )

    def test_partial_jsonl_preserves_complete_rows(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "output"
            path.write_text(json.dumps(self.result([])) + '\n{"query_id":"unfinished"')
            self.assertEqual(completed_rows(path), [self.result([])])


class PublishedEvidenceLocations(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = Path(__file__).with_name("data") / "labels.jsonl"
        cls.labels = {row["query_id"]: row for row in
                      (json.loads(line) for line in path.read_text().splitlines())}

    def test_repeated_net_income_row_is_accepted(self):
        gold = self.labels["query-992438"]
        for start, end in [(126491, 126529), (156887, 156925)]:
            with self.subTest(start=start):
                span = {"document_id": "report-0100", "start": start, "end": end}
                self.assertEqual(evidence_recall(gold, [span])[0], 1.0)

    def test_summary_debt_rows_cover_two_distinct_facts(self):
        spans = [
            {"document_id": "report-0097", "start": 109357, "end": 109408},
            {"document_id": "report-0097", "start": 109413, "end": 109448},
        ]
        self.assertAlmostEqual(
            evidence_recall(self.labels["query-154389"], spans)[0], 2 / 3)

    def test_repeated_total_is_counted_once(self):
        spans = [
            {"document_id": "report-0046", "start": 416910, "end": 416939},
            {"document_id": "report-0046", "start": 417043, "end": 417072},
            {"document_id": "report-0046", "start": 695251, "end": 695280},
        ]
        self.assertEqual(evidence_recall(self.labels["query-687733"], spans)[0], 1.0)

    def test_alternative_row_still_requires_full_coverage_and_correct_report(self):
        gold = self.labels["query-992438"]
        for span in [
            {"document_id": "report-0100", "start": 156887, "end": 156924},
            {"document_id": "report-0097", "start": 156887, "end": 156925},
        ]:
            with self.subTest(span=span):
                self.assertEqual(evidence_recall(gold, [span])[0], 0.0)


if __name__ == "__main__":
    unittest.main()
