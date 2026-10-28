import json
import math
import os
from pathlib import Path
import tempfile
import tomllib
import unittest
from unittest import mock

import grader
import scoring
from finalize_reward import combine


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.order = {str(i): i for i in range(30)}

    def row(self, qid="q", ids=(), scores=None):
        return {"query_id": qid, "results": [{"doc_id": d, "score": s} for d, s in
                zip(ids, scores if scores is not None else range(len(ids), 0, -1))]}

    def test_ndcg_uses_all_positives_and_ten_rank_cap(self):
        self.assertAlmostEqual(scoring.ndcg_at_10(["0"], {"0", "1"}), 1/(1+1/math.log2(3)))
        self.assertEqual(scoring.ndcg_at_10(["0", "1"], {"0", "1"}), 1)
        self.assertEqual(scoring.ndcg_at_10([], {"0"}), 0)
        self.assertEqual(scoring.ndcg_at_10(list(self.order)[:10], set(self.order)), 1)

    def test_output_cardinality_scores_ids_and_order(self):
        self.assertEqual(scoring.validate_row(self.row(), "q", self.order), [])
        cases = [self.row(ids=["0", "0"]), self.row(ids=["missing"]),
                 self.row(ids=list(self.order)[:11]), self.row(ids=["0"], scores=[True]),
                 self.row(ids=["0"], scores=[float("nan")]), self.row(ids=["0"], scores=[float("inf")]),
                 self.row(ids=["0"], scores=["1"]), self.row(ids=["0", "1"], scores=[1, 2]),
                 self.row(ids=["1", "0"], scores=[2, 2]), self.row(qid="wrong")]
        for row in cases:
            with self.subTest(row=row), self.assertRaises(scoring.VerificationError):
                scoring.validate_row(row, "q", self.order)

    def test_strict_json(self):
        for text in ('{"x":1,"x":2}', '{"x":NaN}', '{"x":Infinity}'):
            with self.assertRaises(scoring.VerificationError):
                scoring.strict_json(text)

    def test_batch_coverage_and_arbitrary_query_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "results"
            path.write_text(json.dumps(self.row("b", ["0"])) + "\n" + json.dumps(self.row("a")) + "\n")
            self.assertEqual(grader.read_output(path, {"a", "b"}, self.order), {"b": ["0"], "a": []})
            for data in ([self.row("a")], [self.row("a"), self.row("a")],
                         [self.row("a"), self.row("unknown")], [self.row("a"), {"query_id": []}]):
                path.write_text("\n".join(map(json.dumps, data)))
                with self.assertRaises(scoring.VerificationError):
                    grader.read_output(path, {"a", "b"}, self.order)

    def test_output_must_be_regular_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "good").write_text(json.dumps(self.row()) + "\n")
            (folder / "link").symlink_to(folder / "good")
            with self.assertRaises(OSError):
                grader.read_output(folder / "link", {"q"}, self.order)
            os.mkfifo(folder / "fifo")
            with self.assertRaises(scoring.VerificationError):
                grader.read_output(folder / "fifo", {"q"}, self.order)

    def test_batch_timeout_is_a_whole_task_failure(self):
        with mock.patch.object(grader, "prepare_workspace"), mock.patch.object(grader, "check_boundary"), \
             mock.patch.object(grader, "load_data", return_value=(self.order, [], {})), \
             mock.patch.object(grader, "run_timed", return_value={"timed_out": True, "returncode": None}):
            with self.assertRaises(scoring.VerificationError):
                grader.evaluate()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with mock.patch.object(grader, "prepare_workspace"), mock.patch.object(grader, "check_boundary"), \
                 mock.patch.object(grader, "load_data", return_value=(self.order, [{"query_id": "q", "text": "query"}], {"q": {"0"}})), \
                 mock.patch.object(grader, "INPUT", root), mock.patch.object(grader, "OUTPUT", root), \
                 mock.patch.object(grader.os, "chown"), \
                 mock.patch.object(grader, "run_timed", side_effect=[{"timed_out": False, "returncode": 0}, {"timed_out": True, "returncode": 0}]) as runner:
                with self.assertRaises(scoring.VerificationError):
                    grader.evaluate()
                self.assertEqual(runner.call_args.args[1], 120)

    def test_real_subprocess_deadline(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(grader, "LOGS", Path(tmp)), \
             mock.patch.object(grader, "child_command", side_effect=lambda c: c), \
             mock.patch.object(grader.subprocess, "Popen", wraps=grader.subprocess.Popen) as popen:
            # run_timed uses /app in the real container; use a disposable cwd here.
            real_popen = popen._mock_wraps
            popen.side_effect = lambda *a, **kw: real_popen(*a, **{**kw, "cwd": tmp})
            result = grader.run_timed(["/bin/sleep", "1"], .02, "timeout")
            self.assertTrue(result["timed_out"])

    def test_integrity_gate_fails_closed_and_does_not_normalize_quality(self):
        valid = {"valid": True, "raw_ndcg_at_10": .2, "reward": .2}
        self.assertEqual(combine(valid, {"jailbreak_judge": 1}, "0", True)["reward"], .2)
        for judge, status, trajectory in [({}, "0", True), ({"jailbreak_judge": 0}, "0", True),
                                        ({"jailbreak_judge": 1}, "1", True), ({"jailbreak_judge": 1}, "0", False)]:
            self.assertEqual(combine(valid, judge, status, trajectory)["reward"], 0)
        self.assertEqual(combine({**valid, "valid": False}, {"jailbreak_judge": 1}, "0", True)["reward"], 0)
        self.assertEqual(combine({**valid, "reward": .9}, {"jailbreak_judge": 1}, "0", True)["reward"], 0)

    def test_submission_environment_excludes_judge_credentials(self):
        with mock.patch.dict(os.environ, {"OPENAI_API_KEY": "judge-secret", "CODEX_HOME": "judge-home", "OPENROUTER_API_KEY": "task-key"}):
            command = grader.child_command(["/app/run.sh"])
        self.assertIn("OPENROUTER_API_KEY=task-key", command)
        self.assertIn("--no-new-privs", command)
        self.assertIn("-i", command)
        self.assertFalse(any(x.startswith(("OPENAI_API_KEY=", "OPENAI_BASE_URL=", "CODEX_HOME=")) for x in command))

    def test_frozen_private_data_integrity(self):
        task = Path(__file__).resolve().parents[1]
        with mock.patch.object(grader, "TASK_DATA", task / "data"), mock.patch.object(grader, "PRIVATE", task / "tests/data"):
            corpus, queries, gold = grader.load_data()
        self.assertEqual(len(corpus), 18662)
        self.assertEqual(len(queries), 775)
        metadata = tomllib.loads((task / "task.toml").read_text())["metadata"]
        self.assertEqual(len(queries), metadata["hidden_query_count"])
        examples = grader.read_jsonl(task / "data/examples.jsonl")
        self.assertEqual(len(examples), 6617)
        self.assertFalse({q["query_id"] for q in examples} & gold.keys())
        self.assertFalse({q["text"] for q in examples} & {q["text"] for q in queries})


if __name__ == "__main__":
    unittest.main()
