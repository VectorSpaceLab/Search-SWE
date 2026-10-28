"""Exercise the grader on synthetic files without running a submission or judge."""
import copy
import importlib.util
import io
import json
import tempfile
import tomllib
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch


TASK = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("long_document_grader", TASK / "tests/grader.py")
grader = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(grader)


def encode(rows, **options):
    return "".join(json.dumps(row, **options) + "\n" for row in rows)


class RepeatedOutputTests(unittest.TestCase):
    def setUp(self):
        self.rows = [
            {"query_id": query_id, "results": [
                {"doc_id": f"d{i}", "score": 5 - i} for i in range(5)
            ]}
            for query_id in ("q1", "q2")
        ]

    def run_fixture(self, first, second, second_status=0):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            app = root / "app"
            app.mkdir()
            for name in ("build.sh", "run.sh"):
                script = app / name
                script.write_text("#!/bin/sh\nexit 0\n")
                script.chmod(0o755)
            corpus = root / "corpus.jsonl"
            corpus.write_text(encode([
                {"_id": f"d{i}", "text": f"document {i}"} for i in range(100)
            ]))
            queries = root / "queries.jsonl"
            queries.write_text(encode([
                {"_id": query_id, "text": "synthetic question", "bm25_top_100": [
                    {"doc_id": f"d{i}", "bm25_rank": i + 1, "bm25_score": 100 - i}
                    for i in range(100)
                ]} for query_id in ("q1", "q2")
            ]))
            truth = root / "truth.jsonl"
            truth.write_text(encode([
                {"query_id": "q1", "relevant_doc_ids": ["d0"]},
                {"query_id": "q2", "relevant_doc_ids": ["d99"]},
            ]))
            work = root / "work"
            index = work / "index"
            report = root / "report.json"
            reward = root / "reward.txt"
            commands = []

            def fixture_path(value):
                value = Path(value)
                return app / value.relative_to("/app") if value.is_relative_to("/app") else value

            def run_submission(command, timeout):
                commands.append((command, timeout))
                if command[0] == "/app/build.sh":
                    index.mkdir()
                    (index / "index-data").write_text("synthetic index")
                    return 0, "", ""
                round_index = len(commands) - 2
                output = Path(command[command.index("--output") + 1])
                output.write_text((first, second)[round_index])
                status = second_status if round_index == 1 else 0
                return status, "", "synthetic command failure" if status else ""

            with (
                patch.multiple(grader, CORPUS_PATH=corpus, QUERIES_PATH=queries,
                               GROUND_TRUTH_PATH=truth, WORK_DIR=work, INDEX_DIR=index,
                               INPUT_QUERIES_PATH=work / "input.jsonl",
                               OUTPUT_PATH=work / "first.jsonl",
                               REPEAT_OUTPUT_PATH=work / "second.jsonl",
                               REPORT_PATH=report, REWARD_PATH=reward),
                patch.object(grader, "Path", side_effect=fixture_path),
                patch.object(grader.shutil, "chown"),
                patch.object(grader, "run_submission", side_effect=run_submission),
                patch.object(grader, "stop_starter_service") as cleanup,
                redirect_stdout(io.StringIO()),
            ):
                status = grader.main()
            cleanup.assert_called_once()
            return status, json.loads(report.read_text()), float(reward.read_text()), commands

    def assert_invalid(self, first, second, error):
        status, report, reward, _ = self.run_fixture(first, second)
        self.assertEqual(status, 1)
        self.assertFalse(report["valid"])
        self.assertEqual(reward, 0)
        self.assertIn(error, report["errors"][0])

    def test_valid_format_and_score_differences_are_accepted(self):
        second = copy.deepcopy(self.rows)
        for row in second:
            for result in row["results"]:
                result["score"] = result["score"] / 10 + 0.00001
        status, report, reward, commands = self.run_fixture(
            encode(self.rows, separators=(",", ":")), encode(second, sort_keys=True)
        )
        self.assertEqual(status, 0)
        self.assertTrue(report["valid"])
        self.assertEqual(report["hit_at_5_count"], 1)
        self.assertEqual(reward, 0.5)
        self.assertEqual([timeout for _, timeout in commands], [1800, 3600, 3600])

    def test_valid_different_ranking_keeps_first_round_quality(self):
        second = copy.deepcopy(self.rows)
        second[1]["results"][0]["doc_id"] = "d99"
        status, report, reward, _ = self.run_fixture(encode(self.rows), encode(second))
        self.assertEqual(status, 0)
        self.assertTrue(report["valid"])
        self.assertEqual(reward, 0.5)  # The second invocation would score 1.0.

    def test_second_round_is_checked_against_every_output_rule(self):
        mutations = [
            (lambda rows: rows.pop(), "expected 2 output rows"),
            (lambda rows: rows[0].update(query_id="other"), "query order/ID mismatch"),
            (lambda rows: rows[0]["results"].pop(), "expected exactly 5 results"),
            (lambda rows: rows[0]["results"][0].update(doc_id="unknown"), "outside the candidate pool"),
            (lambda rows: rows[0]["results"][1].update(doc_id="d0"), "duplicate result doc_id"),
            (lambda rows: rows[0]["results"][0].update(score=float("nan")), "non-finite score"),
            (lambda rows: rows[0]["results"][0].update(score=True), "non-finite score"),
            (lambda rows: rows[0]["results"][1].update(score=6), "not non-increasing"),
        ]
        for mutate, error in mutations:
            with self.subTest(error=error, mutation=mutate):
                second = copy.deepcopy(self.rows)
                mutate(second)
                self.assert_invalid(encode(self.rows), encode(second), error)

    def test_second_round_equal_score_tie_order_is_enforced(self):
        second = copy.deepcopy(self.rows)
        second[0]["results"][0].update(doc_id="d1", score=5)
        second[0]["results"][1].update(doc_id="d0", score=5)
        self.assert_invalid(encode(self.rows), encode(second), "not in candidate order")

    def test_second_round_malformed_json_fails(self):
        self.assert_invalid(encode(self.rows), "{broken json}\n", "invalid JSON")

    def test_first_round_invalid_output_still_fails(self):
        first = copy.deepcopy(self.rows)
        first[0]["results"][0]["doc_id"] = "unknown"
        self.assert_invalid(encode(first), encode(self.rows), "outside the candidate pool")

    def test_second_round_command_failure_still_fails(self):
        status, report, reward, _ = self.run_fixture(
            encode(self.rows), encode(self.rows), second_status=7
        )
        self.assertEqual(status, 1)
        self.assertFalse(report["valid"])
        self.assertEqual(reward, 0)
        self.assertIn("run.sh failed with status 7", report["errors"][0])

    def test_outer_budget_covers_existing_repeated_stages_and_judge(self):
        task = tomllib.loads((TASK / "task.toml").read_text())
        judge = tomllib.loads((TASK / "tests/jailbreak_judge/codex.toml").read_text())
        required = grader.BUILD_TIMEOUT + 2 * grader.RUN_TIMEOUT + judge["judge"]["timeout"] + 600
        self.assertGreaterEqual(task["verifier"]["timeout_sec"], required)


if __name__ == "__main__":
    unittest.main()
