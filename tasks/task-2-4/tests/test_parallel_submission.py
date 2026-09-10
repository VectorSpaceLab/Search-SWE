from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location("task2_4_parallel_runner", Path(__file__).with_name("run_submission.py"))
assert SPEC and SPEC.loader
RUNNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNNER)


class ParallelSubmissionTests(unittest.TestCase):
    def exercise(self, fail_query=None):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        submission = root / "submission"
        results = root / "results"
        submission.mkdir()
        for name in ("build.sh", "run.sh"):
            path = submission / name
            path.write_text("#!/bin/sh\nexit 0\n")
            path.chmod(0o755)
        ids = [f"q{i}" for i in range(1, 21)]
        query_path = root / "queries.jsonl"
        query_path.write_text("".join(json.dumps({"query_id": q, "question": q}) + "\n" for q in ids))
        barrier = threading.Barrier(5)
        second_finished = threading.Event()
        lock = threading.Lock()
        stats = {"active": 0, "peak": 0, "builds": 0, "finished": []}

        def fake_run(command, *, cwd, stdout, stderr, timeout):
            if Path(command[0]).name == "build.sh":
                self.assertEqual(timeout, 600)
                stats["builds"] += 1
                return 0, 0.1, None
            self.assertIsNone(timeout)
            input_path = Path(command[command.index("--queries") + 1])
            output_path = Path(command[command.index("--output") + 1])
            qid = json.loads(input_path.read_text())["query_id"]
            with lock:
                stats["active"] += 1
                stats["peak"] = max(stats["peak"], stats["active"])
            if qid in ids[:5]:
                barrier.wait(timeout=5)
            if qid == "q1":
                self.assertTrue(second_finished.wait(timeout=5))
            stdout.write(qid + "\n")
            stderr.write("stderr " + qid + "\n")
            if qid != fail_query:
                output_path.write_text(json.dumps({"query_id": qid, "doc_ids": ["a", "b", "c", "d", "e"]}) + "\n")
            with lock:
                stats["finished"].append(qid)
                stats["active"] -= 1
            if qid == "q2":
                second_finished.set()
            return (7 if qid == fail_query else 0), 0.25, None

        def fake_score(command, **kwargs):
            Path(command[command.index("--report") + 1]).write_text(json.dumps({
                "valid": True, "score": 100.0,
                "primary_metric": {"name": "GoldRecall@5", "value": 1.0},
            }))
            return RUNNER.subprocess.CompletedProcess(command, 0)

        argv = [
            "run_submission.py", "--submission-dir", str(submission),
            "--corpus", str(root / "corpus.jsonl"), "--queries", str(query_path),
            "--qrels", str(root / "qrels.txt"), "--results-dir", str(results),
            "--evaluator", str(root / "evaluate.py"),
        ]
        with patch.object(sys, "argv", argv), \
                patch.object(RUNNER, "prepare_untrusted_tree"), \
                patch.object(RUNNER, "prepare_untrusted_runtime"), \
                patch.object(RUNNER.os, "chown"), \
                patch.object(RUNNER, "run_one", side_effect=fake_run), \
                patch.object(RUNNER.subprocess, "run", side_effect=fake_score) as scorer:
            status = RUNNER.main()
        return ids, results, stats, status, scorer

    def test_five_parallel_queries_keep_outputs_and_logs_in_input_order(self):
        ids, results, stats, status, scorer = self.exercise()
        self.assertEqual(status, 0)
        self.assertEqual(stats["builds"], 1)
        self.assertEqual(stats["peak"], 5)
        self.assertCountEqual(stats["finished"], ids)
        self.assertNotEqual(stats["finished"], ids)
        predictions = [json.loads(line) for line in (results / "results.jsonl").read_text().splitlines()]
        timings = [json.loads(line) for line in (results / "per_query_timings.jsonl").read_text().splitlines()]
        self.assertEqual([row["query_id"] for row in predictions], ids)
        self.assertEqual([row["query_id"] for row in timings], ids)
        for position, qid in enumerate(ids, 1):
            self.assertEqual((results / "query_logs" / f"query-{position:03d}.stdout.log").read_text(), qid + "\n")
        manifest = json.loads((results / "run_manifest.json").read_text())
        self.assertEqual(manifest["phases"]["run"]["query_concurrency"], 5)
        self.assertEqual(manifest["phases"]["run"]["completed"], 20)
        self.assertEqual(manifest["phases"]["run"]["total_query_elapsed_seconds"], 5.0)
        scorer.assert_called_once()

    def test_failed_query_does_not_drop_other_results_and_blocks_scoring(self):
        ids, results, stats, status, scorer = self.exercise(fail_query="q7")
        self.assertEqual(status, 1)
        self.assertCountEqual(stats["finished"], ids)
        report = json.loads((results / "evaluation.json").read_text())
        self.assertFalse(report["valid"])
        self.assertEqual(report["score"], 0.0)
        self.assertIn("query q7: run.sh exited with status 7", report["errors"])
        timings = [json.loads(line) for line in (results / "per_query_timings.jsonl").read_text().splitlines()]
        self.assertEqual(sum(row["returncode"] == 0 for row in timings), 19)
        scorer.assert_not_called()


if __name__ == "__main__":
    unittest.main()
