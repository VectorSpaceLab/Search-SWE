"""Author-side deterministic checks; no model/API calls or host chmods."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import finalize_reward
import grader


class OutputContract(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / "results.jsonl"
        self.queries = [{"query_id": "a", "query": "A research request."}]

    def validate(self, rows):
        self.path.write_text("".join(json.dumps(r) + "\n" for r in rows))
        return grader.validate_output(self.queries, {"d1", "d2"}, output_path=self.path)

    def prediction(self, did="d1", score=0.2):
        return {"query_id": "a", "results": [{"doc_id": did, "score": score}]}

    def test_correct_and_wrong_documents(self):
        for did, expected in [("d1", True), ("d2", False)]:
            rows = self.validate([self.prediction(did)])
            self.assertEqual(grader.score_answers(rows, {"a": "d1"})[0]["correct_at_1"], expected)

    def test_empty_multiple_unknown_and_non_string_documents(self):
        values = [[], [{"doc_id": "d1", "score": 0}] * 2,
                  [{"doc_id": "missing", "score": 0}], [{"doc_id": 1, "score": 0}],
                  [{"score": 0}], None, {}]
        for value in values:
            with self.subTest(value=value), self.assertRaises(grader.VerificationError):
                self.validate([{"query_id": "a", "results": value}])

    def test_invalid_scores(self):
        for value in [True, False, None, "0.2", float("nan"), float("inf"), -float("inf")]:
            with self.subTest(value=value), self.assertRaises(grader.VerificationError):
                self.validate([self.prediction(score=value)])

    def test_duplicate_missing_extra_and_invalid_json(self):
        wrong_id = dict(self.prediction(), query_id="unknown")
        for rows in [[], [wrong_id], [self.prediction()] * 2, [{"query_id": "a"}]]:
            with self.subTest(rows=rows), self.assertRaises(grader.VerificationError):
                self.validate(rows)
        for text in ["bad json\n", "[]\n"]:
            self.path.write_text(text)
            with self.assertRaises(grader.VerificationError):
                grader.validate_output(self.queries, {"d1"}, output_path=self.path)

    def test_output_symlink_is_rejected(self):
        real = self.path.with_name("real.jsonl")
        real.write_text(json.dumps(self.prediction()) + "\n")
        self.path.symlink_to(real)
        with self.assertRaises(grader.VerificationError):
            grader.validate_output(self.queries, {"d1"}, output_path=self.path)

    def test_timeout_ignores_even_a_correct_answer(self):
        row = dict(self.prediction(), timed_out=True)
        self.assertFalse(grader.score_answers([row], {"a": "d1"})[0]["correct_at_1"])
        row["results"] = []
        self.assertFalse(grader.score_answers([row], {"a": "d1"})[0]["correct_at_1"])


class QueryDeadline(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.queries = [{"query_id": x, "query": x} for x in "abc"]
        patches = patch.multiple(grader, OUTPUT_DIR=self.root, RESULTS_DIR=self.root)
        patches.start()
        self.addCleanup(patches.stop)

    def stage(self, rows, *, filename):
        self.assertEqual(len(rows), 1)
        path = self.root / ("input-" + filename)
        path.write_text(json.dumps(rows[0]) + "\n")
        return path

    def success(self, command, **kwargs):
        self.assertEqual(kwargs["timeout"], 30)
        self.assertEqual(command[command.index("--top-k") + 1], "1")
        query = json.loads(Path(command[command.index("--queries") + 1]).read_text())
        output = Path(command[command.index("--output") + 1])
        self.assertFalse(output.exists())
        output.write_text(json.dumps({"query_id": query["query_id"], "results": [{"doc_id": "d1", "score": 0.5}]}) + "\n")
        return {"returncode": 0, "timed_out": False, "elapsed_seconds": .1}

    def test_timeout_continues_with_unique_paths(self):
        calls = []
        def run(command, **kwargs):
            calls.append(command)
            result = self.success(command, **kwargs)
            if len(calls) == 2:
                result.update(returncode=-9, timed_out=True, elapsed_seconds=30.2)
            return result
        metrics = {}
        with patch.object(grader, "stage_queries", side_effect=self.stage), patch.object(grader, "run_timed", side_effect=run):
            rows = grader.run_queries(self.queries, {"d1"}, metrics)
        scored = grader.score_answers(rows, {x: "d1" for x in "abc"})
        self.assertEqual([r["correct_at_1"] for r in scored], [True, False, True])
        self.assertEqual(rows[1]["results"], [])
        self.assertEqual(len({c[c.index("--output") + 1] for c in calls}), 3)
        self.assertEqual(metrics["per_query_timeout_seconds"], 30)

    def test_nonzero_exit_and_missing_output_invalidate_submission(self):
        for rc in [7, 0]:
            with self.subTest(returncode=rc), patch.object(grader, "stage_queries", side_effect=self.stage), \
                 patch.object(grader, "run_timed", return_value={"returncode": rc, "timed_out": False, "elapsed_seconds": .1}), \
                 self.assertRaises(grader.VerificationError):
                grader.run_queries(self.queries, {"d1"}, {})

    def test_actual_child_timeout(self):
        with patch.object(grader, "submission_command", side_effect=lambda x: x), patch.object(grader, "SUBMISSION_DIR", self.root):
            result = grader.run_timed(["/bin/sh", "-c", "sleep 10"], timeout=.15,
                                      stdout_path=self.root / "stdout", stderr_path=self.root / "stderr")
        self.assertTrue(result["timed_out"])
        self.assertLess(result["elapsed_seconds"], 2)

    def test_fractional_reward_counts_timeouts_in_denominator(self):
        count = 0
        def run(command, **kwargs):
            nonlocal count
            if command[0].endswith("build.sh"):
                return {"returncode": 0, "timed_out": False, "elapsed_seconds": .1}
            count += 1
            if count == 2:
                return {"returncode": -9, "timed_out": True, "elapsed_seconds": 30.2}
            return self.success(command, **kwargs)
        report = self.root / "evaluation.json"
        with patch.multiple(grader, REPORT_PATH=report, EXECUTION_ERROR=""), \
             patch.object(grader, "recreate_workdirs"), patch.object(grader, "load_corpus", return_value={"d1"}), \
             patch.object(grader, "load_private_data", return_value=(self.queries, {x: "d1" for x in "abc"})), \
             patch.object(grader, "check_submission_boundary"), patch.object(grader, "stop_submission_processes"), \
             patch.object(grader, "stage_queries", side_effect=self.stage), patch.object(grader, "run_timed", side_effect=run), \
             patch("builtins.print"):
            grader.main()
        value = json.loads(report.read_text())
        self.assertTrue(value["valid"])
        self.assertEqual(value["reward"], 2 / 3)
        self.assertEqual(value["timed_out_queries"], 1)


class IntegrityGate(unittest.TestCase):
    def test_only_submission_keys_are_forwarded(self):
        with patch.dict("os.environ", {"OPENAI_API_KEY": "judge-placeholder", "OPENAI_BASE_URL": "judge-host",
                                      "OPENROUTER_API_KEY": "retrieval-placeholder", "JINA_API_KEY": "embedding-placeholder"}):
            command = grader.submission_command(["/app/run.sh"])
        self.assertIn("OPENROUTER_API_KEY=retrieval-placeholder", command)
        self.assertIn("JINA_API_KEY=embedding-placeholder", command)
        self.assertFalse(any(x.startswith(("OPENAI_API_KEY=", "OPENAI_BASE_URL=", "CODEX_HOME=")) for x in command))
        self.assertIn("--no-new-privs", command)

    def test_missing_failed_or_rejecting_judge_cannot_award_reward(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evaluation = root / "evaluation.json"
            evaluation.write_text(json.dumps({"valid": True, "primary_metric": {"value": .625}}))
            reward = root / "reward.json"
            trajectory = root / "trajectory.json"
            trajectory.write_text("{}")
            with patch.multiple(finalize_reward, REWARD_DIR=root, EVALUATION_PATH=evaluation,
                                JUDGE_REWARD_PATH=reward, DETAILS_PATH=root / "details.json", TRAJECTORY_PATH=trajectory), patch("builtins.print"):
                for status, judgment, expected in [("0", 1, .625), ("0", 0, 0), ("0", .5, 0), ("1", 1, 0), ("", 1, 0)]:
                    reward.write_text(json.dumps({"jailbreak_judge": judgment}))
                    with patch.object(finalize_reward, "JUDGE_STATUS", status):
                        finalize_reward.main()
                    self.assertEqual(json.loads(reward.read_text())["reward"], expected)
                    self.assertEqual(float((root / "reward.txt").read_text()), expected)
                trajectory.unlink()
                reward.write_text('{"jailbreak_judge":1}')
                with patch.object(finalize_reward, "JUDGE_STATUS", "0"):
                    finalize_reward.main()
                self.assertEqual(json.loads(reward.read_text())["reward"], 0)


if __name__ == "__main__":
    unittest.main()
