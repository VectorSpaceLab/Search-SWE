import unittest
from evaluation import check_retrieval, answer_request, check_answer, fama


class TemporalRecords(unittest.TestCase):
    def setUp(self):
        self.query = {
            "query_id": "q",
            "persona_id": "p",
            "cutoff_session": 3,
            "question": "What changed?",
        }
        self.records = {
            "current": {
                "record_id": "current",
                "persona_id": "p",
                "session_id": 3,
                "date": "DATE",
                "text": "complete " * 2000,
            },
            "future": {
                "record_id": "future",
                "persona_id": "p",
                "session_id": 4,
                "text": "future",
            },
            "other": {
                "record_id": "other",
                "persona_id": "other",
                "session_id": 1,
                "text": "other",
            },
        }

    def result(self, ids):
        return {"query_id": "q", "record_ids": ids}

    def test_current_and_empty(self):
        self.assertEqual(
            check_retrieval(self.query, self.result(["current"]), self.records),
            ["current"],
        )
        self.assertEqual(check_retrieval(self.query, self.result([]), self.records), [])

    def test_person_cutoff_missing_duplicate(self):
        for ids in [["future"], ["other"], ["missing"], ["current", "current"]]:
            with self.subTest(ids=ids), self.assertRaises(ValueError):
                check_retrieval(self.query, self.result(ids), self.records)

    def test_350_limit(self):
        records = {
            str(i): dict(self.records["current"], record_id=str(i)) for i in range(351)
        }
        check_retrieval(self.query, self.result(list(records)[:350]), records)
        with self.assertRaises(ValueError):
            check_retrieval(self.query, self.result(list(records)), records)

    def test_full_original_record_assembly(self):
        payload = answer_request(self.query, ["current"], self.records)
        self.assertEqual(payload["records"], [self.records["current"]])
        self.assertEqual(len(payload["records"][0]["text"]), 18000)
        self.assertEqual(payload["question"], self.query["question"])

    def test_exact_answer_interface(self):
        self.assertEqual(
            check_answer(self.query, {"query_id": "q", "answer": "Fine."})["answer"],
            "Fine.",
        )
        for row in [
            {"query_id": "bad", "answer": "Fine."},
            {"query_id": "q", "answer": " "},
            {"query_id": "q", "answer": "Fine.", "record_ids": ["current"]},
        ]:
            with self.subTest(row=row), self.assertRaises(ValueError):
                check_answer(self.query, row)

    def test_exact_retrieval_interface(self):
        for row in [
            {"query_id": "bad", "record_ids": []},
            {"query_id": "q", "record_ids": "current"},
            {"query_id": "q", "record_ids": [], "answer": "extra"},
        ]:
            with self.subTest(row=row), self.assertRaises(ValueError):
                check_retrieval(self.query, row, self.records)


class AtomicCriteria(unittest.TestCase):
    def gold(self, criteria):
        return {
            "criteria": [
                {"kind": kind, "expected_answer": expected}
                for kind, expected in criteria
            ]
        }

    def test_individual_scores_are_averaged(self):
        gold = self.gold([("memory_presence", "yes"), ("forgetting_absence", "no")])
        score, details = fama(gold, [["yes", "no"], ["yes", "no"], ["no", "yes"]])
        self.assertAlmostEqual(score, 2/3)
        self.assertEqual([m["fama"] for m in details["judge_measurements"]], [1, 1, 0])
        self.assertEqual(details["aggregation"], "mean")

    def test_failed_forgetting_reduces_score_by_its_fraction(self):
        gold = self.gold(
            [
                ("memory_presence", "yes"),
                ("memory_presence", "yes"),
                ("forgetting_absence", "no"),
            ]
        )
        score, _ = fama(gold, [["yes", "yes", "yes"]] * 3)
        self.assertAlmostEqual(score, 2 / 3)

    def test_score_does_not_become_negative(self):
        gold = self.gold([("memory_presence", "yes"), ("forgetting_absence", "no")])
        self.assertEqual(fama(gold, [["no", "yes"]] * 3)[0], 0)

    def test_no_forgetting_criteria_have_no_penalty(self):
        gold = self.gold([("memory_presence", "yes"), ("memory_presence", "yes")])
        self.assertEqual(fama(gold, [["yes", "no"]] * 3)[0], 0.5)

    def test_incomplete_or_unrecognized_votes_are_invalid(self):
        gold = self.gold([("memory_presence", "yes")])
        for panels in [
            [["yes"]] * 2,
            [["yes"], ["yes"], []],
            [["yes"], ["yes"], ["maybe"]],
        ]:
            with self.subTest(panels=panels), self.assertRaises(ValueError):
                fama(gold, panels)

    def test_unknown_criterion_is_invalid(self):
        with self.assertRaises(ValueError):
            fama(self.gold([("unrecognized", "yes")]), [["yes"]] * 3)


if __name__ == "__main__":
    unittest.main()
