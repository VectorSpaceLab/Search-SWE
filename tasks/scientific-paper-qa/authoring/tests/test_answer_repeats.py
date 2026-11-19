"""Offline evidence-gated repeated answer judging and failure propagation."""

import io
import json
import sys
import tempfile
import urllib.error
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(TASK_ROOT / "tests"))

import unittest
from unittest.mock import patch

import grader


class AnswerRepeatTests(unittest.TestCase):
    def run_grade(self, responses, evidence="doc", *, directory=None, answer="fixed answer", model="model"):
        if directory is None:
            directory = self.enterContext(tempfile.TemporaryDirectory())
        queries = [{"query_id": "q", "question": "question"}]
        gold = {"q": {"evidence": "doc", "answer": "reference"}}
        prediction = {"q": {"evidence": evidence, "answer": answer}}
        with patch.object(grader, "load_reference_data", return_value=(queries, gold, {"doc"})), \
                patch.object(grader, "load_predictions", return_value=prediction), \
                patch.object(grader, "judge_config", return_value=grader.JudgeConfig("base", "key", model)), \
                patch.object(grader, "call_judge", side_effect=responses) as judge, \
                patch.object(grader, "RESULTS_DIR", Path(directory)), \
                patch.object(grader, "write_report") as write, \
                patch.object(grader, "EXECUTION_ERROR", ""):
            status = grader.main()
        return status, write.call_args.args[0], judge

    def test_averages_three_decisions_without_majority_vote(self):
        values = [json.dumps({"correct": value}) for value in [True, True, False]]
        status, report, judge = self.run_grade(values)
        self.assertEqual(status, 0)
        self.assertTrue(report["valid"])
        self.assertAlmostEqual(report["primary_metric"]["value"], 2 / 3)
        self.assertEqual(judge.call_count, 3)
        self.assertEqual(len(report["per_query_metrics"][0]["judge_samples"]), 3)
        self.assertTrue(all(call.kwargs["candidate_answer"] == "fixed answer" for call in judge.call_args_list))

    def test_wrong_evidence_never_calls_answer_judge(self):
        status, report, judge = self.run_grade([], evidence="wrong")
        self.assertEqual(status, 0)
        self.assertEqual(report["primary_metric"]["value"], 0)
        judge.assert_not_called()

    def test_partial_or_malformed_judging_invalidates_measurement(self):
        for last in [RuntimeError("judge unavailable"), "malformed"]:
            with self.subTest(last=last):
                status, report, judge = self.run_grade(['{"correct":true}', last])
                self.assertEqual(status, 1)
                self.assertFalse(report["valid"])
                self.assertEqual(report["primary_metric"]["value"], 0)
                self.assertEqual(report["answer_judge_call_count"], 2)
                self.assertTrue(report["errors"])

    def test_restart_preserves_both_negative_and_positive_votes(self):
        with tempfile.TemporaryDirectory() as directory:
            status, _, _ = self.run_grade(['{"correct":false}', '{"correct":true}', OSError("offline")],
                                          directory=directory)
            self.assertEqual(status, 1)
            status, report, judge = self.run_grade(['{"correct":true}'], directory=directory)
            self.assertEqual(status, 0)
            judge.assert_called_once()
            samples = report["per_query_metrics"][0]["judge_samples"]
            self.assertEqual([vote["from_checkpoint"] for vote in samples], [True, True, False])
            self.assertAlmostEqual(report["primary_metric"]["value"], 2 / 3)
            for changes in ({"answer": "different"}, {"model": "different"}):
                with self.subTest(changes=changes):
                    _, _, judge = self.run_grade(['{"correct":false}'] * 3, directory=directory, **changes)
                    self.assertEqual(judge.call_count, 3)

    def judge_requests(self, replies, *, fails=False):
        def reply(item):
            if isinstance(item, Exception):
                return item
            content, finish = item
            body = {"choices": [{"message": {"content": content}, "finish_reason": finish}]}
            return io.BytesIO(json.dumps(body).encode())

        with patch.object(grader.urllib.request, "urlopen", side_effect=[reply(item) for item in replies]) as post, \
                patch.object(grader.time, "sleep"):
            args = dict(question="q", candidate_answer="a", reference_answer="g")
            config = grader.JudgeConfig("https://example.invalid", "test", "model")
            if fails:
                with self.assertRaises(ValueError):
                    grader.call_judge(config, **args)
            else:
                result = grader.call_judge(config, **args)
                self.assertEqual(json.loads(result), {"correct": False})
        return [json.loads(call.args[0].data)["max_tokens"] for call in post.call_args_list]

    def test_only_an_unparseable_length_limited_vote_raises_the_budget(self):
        valid = '{"correct":false}'
        self.assertEqual(self.judge_requests([(None, "length"), ('{"correct":', "length"), (valid, "stop")]),
                         [512, 2048, 8192])
        self.assertEqual(self.judge_requests([(valid, "length")]), [512])

    def test_transport_empty_and_malformed_replies_retry_within_one_vote(self):
        valid = ('{"correct":false}', "stop")
        self.assertEqual(self.judge_requests([urllib.error.URLError("offline"), ("", "stop"), valid]),
                         [512, 512, 512])
        self.assertEqual(self.judge_requests([("invalid", "stop"), valid]), [512, 512])
        self.assertEqual(self.judge_requests([("invalid", "stop")] * 3, fails=True), [512, 512, 512])


if __name__ == "__main__":
    unittest.main()
