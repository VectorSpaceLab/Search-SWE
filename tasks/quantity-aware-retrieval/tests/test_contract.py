import math
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import scoring
import grader
from finalize_reward import combine


class ScoringContract(unittest.TestCase):
    def setUp(self):
        self.order = {str(i): i for i in range(30)}

    def row(self, ids, scores=None):
        return {"query_id": "q", "results": [{"doc_id": d, "score": s} for d, s in
            zip(ids, scores if scores is not None else range(len(ids), 0, -1))]}

    def test_ndcg_uses_all_relevant_documents(self):
        self.assertAlmostEqual(scoring.ndcg_at_10(["0"], {"0", "1"}), 1/(1+1/math.log2(3)))
        self.assertEqual(scoring.ndcg_at_10(["0", "1"], {"0", "1"}), 1)
        self.assertEqual(scoring.ndcg_at_10([], {"0"}), 0)
        self.assertEqual(scoring.ndcg_at_10([str(i) for i in range(10)], set(self.order)), 1)

    def test_normalization_at_baseline_and_perfect(self):
        b = grader.BASELINE_NDCG
        self.assertEqual(scoring.normalized_reward(b, b), 0)
        self.assertEqual(scoring.normalized_reward(0, b), 0)
        self.assertEqual(scoring.normalized_reward(1, b), 1)
        self.assertAlmostEqual(scoring.normalized_reward((1+b)/2, b), .5)

    def test_optional_short_rankings(self):
        self.assertEqual(scoring.validate_row(self.row([]), "q", self.order), [])
        self.assertEqual(scoring.validate_row(self.row(["0", "2"]), "q", self.order), ["0", "2"])

    def test_reject_invalid_output(self):
        cases = [self.row(["0", "0"]), self.row(["unknown"]), self.row([str(i) for i in range(11)]),
                 self.row(["0"], [True]), self.row(["0"], [float("nan")]),
                 self.row(["0"], [float("inf")]), self.row(["0"], ["1"]),
                 self.row(["0", "1"], [1, 2]), self.row(["1", "0"], [2, 2]),
                 {"query_id": "wrong", "results": []}]
        for row in cases:
            with self.subTest(row=row), self.assertRaises(scoring.VerificationError):
                scoring.validate_row(row, "q", self.order)

    def test_duplicate_json_keys_and_nonfinite_constants(self):
        for value in ['{"x":1,"x":2}', '{"x":NaN}', '{"x":Infinity}']:
            with self.assertRaises(scoring.VerificationError):
                scoring.strict_json(value)

    def test_output_file_boundary(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            (p / "good").write_text('{"query_id":"q","results":[]}\n')
            self.assertEqual(grader.read_output(p / "good", "q", self.order), [])
            (p / "link").symlink_to(p / "good")
            with self.assertRaises(OSError):
                grader.read_output(p / "link", "q", self.order)
            (p / "large").write_text(" " * 65537 + '{"query_id":"q","results":[]}\n')
            self.assertEqual(grader.read_output(p / "large", "q", self.order), [])
            (p / "multiple").write_text('{"query_id":"q","results":[]}\n'*2)
            with self.assertRaises(scoring.VerificationError):
                grader.read_output(p / "multiple", "q", self.order)

    def test_judge_failures_cannot_produce_positive_reward(self):
        evaluation = {"valid": True, "raw_ndcg_at_10": .7, "reward": .5}
        self.assertEqual(combine(evaluation, {"jailbreak_judge": 1}, "0", True)["reward"], .5)
        for judge, status, trajectory in [({}, "0", True), ({"jailbreak_judge": 0}, "0", True),
                ({"jailbreak_judge": 1}, "1", True), ({"jailbreak_judge": 1}, "0", False),
                ({"jailbreak_judge": .5}, "0", True)]:
            self.assertEqual(combine(evaluation, judge, status, trajectory)["reward"], 0)
        self.assertEqual(combine({"valid": False, "reward": 1}, {"jailbreak_judge": 1}, "0", True)["reward"], 0)

    def test_submission_environment_excludes_judge_credentials(self):
        with mock.patch.dict("os.environ", {"OPENAI_API_KEY": "judge-secret", "OPENAI_BASE_URL": "judge-endpoint",
                                           "CODEX_HOME": "judge-home", "OPENROUTER_API_KEY": "task-key"}):
            command = grader.child_command(["/app/run.sh"])
        self.assertIn("OPENROUTER_API_KEY=task-key", command)
        self.assertIn("--no-new-privs", command)
        self.assertIn("-i", command)
        self.assertFalse(any(x.startswith(("OPENAI_API_KEY=", "OPENAI_BASE_URL=", "CODEX_HOME=")) for x in command))


if __name__ == "__main__":
    unittest.main()
