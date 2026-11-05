"""Exercise the production repetition loop without GPU work or privileged commands."""
from contextlib import ExitStack
from pathlib import Path
import re
import tempfile
import tomllib
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import grader


class TimingTests(unittest.TestCase):
    def evaluate_fixture(self, *, bad_quality_run=None):
        case = self
        times = [0.1, 0.7, 0.8, 0.2, 0.3]
        instances = []
        corpus = {"relevant": ("corpus1", 0), "other": ("corpus1", 1)}
        queries = [{"query_id": "hidden", "collection": "corpus1", "text": "query"}]
        gold = {"hidden": {"collection": "corpus1", "relevance": {"relevant": 1}}}
        warmup = [{"query_id": "warmup", "collection": "corpus1", "text": "example"}]

        class Service:
            def __init__(self, scratch, label):
                case.assertEqual(list(scratch.iterdir()), [])
                (scratch / "service-state").write_text(label)
                self.scratch = scratch
                self.repeat = len(instances)
                self.requests = []
                self.ready_called = False
                self.closed = False
                instances.append(self)

            def ready(self):
                self.ready_called = True

            def request(self, rows, seconds):
                case.assertTrue(self.ready_called)
                self.requests.append((rows, seconds))
                warming_up = len(self.requests) == 1
                document = "other" if not warming_up and self.repeat == bad_quality_run else "relevant"
                response = {"results": [
                    {"query_id": q["query_id"], "results": [{"doc_id": document, "score": 1}]}
                    for q in rows
                ]}
                return response, 0.01 if warming_up else times[self.repeat]

            def close(self):
                self.closed = True

        with tempfile.TemporaryDirectory() as temporary, ExitStack() as stack:
            root = Path(temporary)
            logs, work = root / "logs", root / "work"
            logs.mkdir()
            replacements = {
                "LOGS": logs, "WORK": work, "INDEX": work / "index", "QUERY_COUNT": 1,
                "load_data": lambda: (corpus, queries, gold, warmup),
                "directory": lambda path, candidate=False: path.mkdir(mode=0o700),
                "Service": Service,
            }
            for name, value in replacements.items():
                stack.enter_context(patch.object(grader, name, value))
            stack.enter_context(patch.object(grader, "boundary"))
            stack.enter_context(patch.object(grader, "stop_children"))
            frozen = stack.enter_context(patch.object(grader, "freeze"))
            build = stack.enter_context(patch.object(
                grader.subprocess, "run", return_value=SimpleNamespace(returncode=0)))
            report = grader.evaluate()
            build.assert_called_once()
            frozen.assert_called_once_with(work / "index")
            self.assertEqual(len(instances), 5)
            self.assertEqual(len({s.scratch for s in instances}), 5)
            for service in instances:
                self.assertTrue(service.closed)
                self.assertFalse(service.scratch.exists())
                self.assertEqual(len(service.requests), 2)
                self.assertEqual(service.requests[0], (warmup, grader.WARMUP_SECONDS))
                self.assertEqual(service.requests[1][1], grader.QUERY_SECONDS)
            self.assertEqual([r["elapsed_seconds"] for r in report["runs"]], times)
            return report

    def test_five_fresh_services_share_one_build_and_use_median(self):
        report = self.evaluate_fixture()
        self.assertEqual(report["median_query_seconds"], 0.3)
        self.assertEqual(report["ndcg_at_10"], 1.0)
        self.assertTrue(report["quality_gate_passed"])
        self.assertAlmostEqual(report["reward"], 0.625)

    def test_fifth_run_must_also_pass_quality_gate(self):
        report = self.evaluate_fixture(bad_quality_run=4)
        self.assertEqual(report["median_query_seconds"], 0.3)
        self.assertEqual(report["ndcg_at_10"], 0.0)
        self.assertFalse(report["quality_gate_passed"])
        self.assertEqual(report["reward"], 0.0)

    def test_nested_timeouts_cover_all_five_runs_and_audit(self):
        task = Path(__file__).resolve().parent.parent
        config = tomllib.loads((task / "task.toml").read_text())
        self.assertEqual(config["metadata"]["timing_repeats"], grader.REPEATS)
        self.assertEqual(grader.REPEATS, 5)
        wrappers = [(int(grace), int(limit)) for grace, limit in re.findall(
            r"--kill-after=(\d+)s\s+(\d+)s", (task / "tests/test.sh").read_text())]
        self.assertEqual(len(wrappers), 3)
        candidate_budget = grader.BUILD_SECONDS + grader.REPEATS * (
            grader.LOAD_SECONDS + grader.WARMUP_SECONDS + grader.QUERY_SECONDS)
        self.assertGreater(wrappers[0][1], candidate_budget)
        self.assertGreater(config["verifier"]["timeout_sec"],
                           sum(grace + limit for grace, limit in wrappers))


if __name__ == "__main__":
    unittest.main()
