"""Offline author checks for output integrity, deadlines and fail-closed scoring."""

import copy
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import faiss
import numpy as np
from scipy.sparse import csr_matrix

from checks import check_result
import configure_trajectory_judge
import finalize_reward
from grader import Process, check_index_files, check_quality, inspect_faiss, run_stage


class ResultContractTests(unittest.TestCase):
    def setUp(self):
        self.vectors = np.array([[0], [1], [1], [4]], dtype=np.uint8)
        self.metadata = csr_matrix([[1], [1], [1], [0]])
        self.query = {"query_id": "example", "vector": [0], "filter": {"all": [0]}, "k": 2}
        self.gold = {"eligible_count": 3, "distances": [0.0, 1.0]}
        self.result = {"query_id": "example", "results": [
            {"doc_id": 0, "distance": 0.0}, {"doc_id": 2, "distance": 1.0}]}

    def check(self, result):
        return check_result(self.query, result, self.gold, self.vectors, self.metadata)

    def test_valid_boundary_tie_is_accepted(self):
        self.assertEqual(self.check(self.result), 1.0)

    def test_malformed_or_incorrect_outputs_fail(self):
        changes = [
            lambda result: result.update(query_id="wrong"),
            lambda result: result.update(results=[]),
            lambda result: result["results"][1].update(doc_id=0, distance=0.0),
            lambda result: result["results"][1].update(doc_id=4),
            lambda result: result["results"][1].update(doc_id=3, distance=16.0),
            lambda result: result["results"][1].update(distance=float("nan")),
            lambda result: result["results"][1].update(distance=2.0),
            lambda result: result["results"].reverse(),
        ]
        for number, change in enumerate(changes):
            with self.subTest(case=number):
                result = copy.deepcopy(self.result)
                change(result)
                with self.assertRaises(ValueError):
                    self.check(result)

    def test_zero_k_accepts_only_empty_results(self):
        self.query["k"] = 0
        self.assertEqual(self.check({"query_id": "example", "results": []}), 1.0)
        with self.assertRaises(ValueError):
            self.check(self.result)

    def test_scores_average_over_all_ten_cases(self):
        for passed in [0, 1, 7, 9, 10]:
            with self.subTest(passed=passed):
                cases = [{"query_id": str(i), "score": int(i < passed)} for i in range(10)]
                self.assertEqual(check_quality({"queries": cases}), passed / 10)

    def test_missing_or_duplicate_case_fails(self):
        for count in [9, 10]:
            with self.subTest(count=count), self.assertRaises(ValueError):
                check_quality({"queries": [{"query_id": "same", "score": 1}] * count})


class IndependentQueryTests(unittest.TestCase):
    def test_failures_do_not_abort_or_contaminate_other_queries(self):
        # Exercise build -> queries -> relocation -> replay aggregation. A
        # failed first replay must not earn credit from a successful second one.
        for failure in [None, "recall", "timeout", "malformed", "exit", "wrong_id", "replay", "all"]:
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                corpus = root / "corpus"
                corpus.mkdir()
                queries = [{"query_id": str(i), "vector": [0], "filter": {"all": [0]}, "k": 2}
                           for i in range(10)]
                gold = [{"query_id": q["query_id"], "eligible_count": 3,
                         "distances": [0.0, 1.0], "group": "synthetic"} for q in queries]
                (root / "queries.jsonl").write_text("\n".join(map(json.dumps, queries)))
                (root / "gold.jsonl").write_text("\n".join(map(json.dumps, gold)))
                processes, attempts, startup_timeouts = [], [], []

                class Submission:
                    def __init__(self, command, app, work, log, run_as, threads):
                        self.reloaded = work.name == "restored-index"
                        self.closed = False
                        processes.append(self)

                    def build_wait(self, timeout):
                        pass

                    def readline(self, timeout=None):
                        startup_timeouts.append(timeout)
                        return {"status": "ready"}

                    def request(self, query, timeout):
                        attempts.append((self.reloaded, query["query_id"]))
                        result = {"query_id": query["query_id"], "results": [
                            {"doc_id": 0, "distance": 0.0}, {"doc_id": 1, "distance": 1.0}]}
                        if failure == "all" or (query["query_id"] == "3" and not self.reloaded):
                            if failure in ["timeout", "all"]:
                                raise TimeoutError("late answer")
                            if failure == "malformed":
                                raise ValueError("invalid JSON")
                            if failure == "exit":
                                raise RuntimeError("process exited before replying")
                            if failure == "wrong_id":
                                result["query_id"] = "wrong"
                            if failure == "recall":
                                result["results"] = [{"doc_id": 1, "distance": 1.0},
                                                     {"doc_id": 2, "distance": 1.0}]
                        if failure == "replay" and self.reloaded and query["query_id"] == "3":
                            result["results"][1]["doc_id"] = 2
                        return result, 0.001

                    def close(self):
                        self.closed = True

                args = SimpleNamespace(app=root, work_dir=root / "work", run_as="",
                                       report=root / "evaluation.json")
                with patch("grader.Process", Submission), \
                        patch("grader.read_vectors", return_value=np.array([[0], [1], [1]], dtype=np.uint8)), \
                        patch("grader.read_metadata", return_value=csr_matrix([[1], [1], [1]])), \
                        patch("grader.inspect_faiss", return_value={}):
                    report = run_stage(args, "retrieval", corpus, root / "queries.jsonl",
                                       root / "gold.jsonl")
                expected = 1.0 if failure is None else 0.0 if failure == "all" else 0.9
                self.assertEqual(check_quality(report), expected)
                self.assertEqual(report["mean_score"], expected)
                self.assertEqual(len(attempts), 20)
                self.assertEqual(len(set(attempts)), 20)
                self.assertTrue(all(p.closed for p in processes))
                self.assertTrue(startup_timeouts)
                self.assertTrue(all(timeout is None for timeout in startup_timeouts))
                if failure not in [None, "all"]:
                    self.assertEqual(report["queries"][3]["score"], 0)
                    self.assertTrue(all(q["score"] == 1 for q in report["queries"][4:]))
                if failure in ["timeout", "malformed", "exit", "wrong_id"]:
                    self.assertEqual(len(processes), 4)  # build, first service, recovery, replay


class IndexAndDeadlineTests(unittest.TestCase):
    def test_slow_startup_does_not_consume_the_query_deadline(self):
        for response_seconds in [0.005, 0.02]:
            with self.subTest(response_seconds=response_seconds):
                clock, waits = [0.0], []
                messages = iter([b'{"status":"ready"}\n', b'{"query_id":"q","results":[]}\n'])
                process = Process.__new__(Process)
                process.proc = SimpleNamespace(
                    stdin=SimpleNamespace(fileno=lambda: 123),
                    stdout=SimpleNamespace(fileno=lambda: 124))
                process.buffer = bytearray()

                def select(timeout):
                    duration = 120.0 if not waits else response_seconds
                    waits.append(timeout)
                    if timeout is not None and duration > timeout:
                        clock[0] += timeout
                        return []
                    clock[0] += duration
                    return [(None, None)]

                def write(_fd, payload):
                    clock[0] += 0.001
                    return len(payload)

                process.selector = SimpleNamespace(select=select)
                with patch("grader.time.monotonic", side_effect=lambda: clock[0]), \
                        patch("grader.os.read", side_effect=lambda *_: next(messages)), \
                        patch("grader.os.write", side_effect=write):
                    self.assertEqual(process.readline(), {"status": "ready"})
                    self.assertEqual(clock[0], 120.0)
                    self.assertIsNone(waits[0])
                    if response_seconds > 0.015:
                        with self.assertRaises(TimeoutError):
                            process.request({"query_id": "q"}, 0.015)
                    else:
                        _, elapsed = process.request({"query_id": "q"}, 0.015)
                        self.assertAlmostEqual(elapsed, 0.006)

    def test_exit_before_ready_fails_without_a_load_deadline(self):
        process = Process.__new__(Process)
        process.proc = SimpleNamespace(stdout=SimpleNamespace(fileno=lambda: 123))
        process.buffer = bytearray()
        process.selector = SimpleNamespace(select=lambda timeout: [(None, None)])
        with patch("grader.os.read", return_value=b""):
            with self.assertRaisesRegex(RuntimeError, "closed stdout"):
                process.readline()

    def test_large_index_files_are_allowed_but_symlinks_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            # A sparse file crosses the removed 12 GiB gate without using disk space.
            with (root / "vectors.bin").open("wb") as handle:
                handle.truncate(13 * 1024 ** 3)
            check_index_files(root)
            (root / "outside-link").symlink_to(root / "vectors.bin")
            with self.assertRaisesRegex(ValueError, "symbolic links"):
                check_index_files(root)

    def test_ann_index_is_accepted_and_exact_only_index_is_rejected(self):
        vectors = np.array([[0.0], [1.0]], dtype=np.float32)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for index, accepted in [(faiss.IndexHNSWFlat(1, 2), True),
                                    (faiss.IndexFlatL2(1), False)]:
                index.add(vectors)
                faiss.write_index(index, str(root / "index.faiss"))
                if accepted:
                    self.assertEqual(inspect_faiss(root, 2, 1)["ntotal"], 2)
                else:
                    with self.assertRaises(ValueError):
                        inspect_faiss(root, 2, 1)

    def test_deadline_includes_request_write_and_json_decode(self):
        for write_time, response_time, fails in [(0.002, 0.004, False), (0.004, 0.007, True)]:
            with self.subTest(write=write_time, response=response_time):
                clock = [0.0]
                process = Process.__new__(Process)
                process.proc = SimpleNamespace(stdin=SimpleNamespace(fileno=lambda: 123))

                def write(_fd, payload):
                    clock[0] += write_time
                    return len(payload)

                def response(_timeout):
                    clock[0] += response_time
                    return {"query_id": "deadline", "results": []}

                process.readline = response
                with patch("grader.time.monotonic", side_effect=lambda: clock[0]), \
                        patch("grader.os.write", side_effect=write):
                    if fails:
                        with self.assertRaises(TimeoutError):
                            process.request({"query_id": "deadline"}, 0.01)
                    else:
                        _, elapsed = process.request({"query_id": "deadline"}, 0.01)
                        self.assertAlmostEqual(elapsed, 0.006)


class FinalGateTests(unittest.TestCase):
    def test_retrieval_trajectory_and_audit_are_all_required(self):
        cases = [
            (True, 10, 1.0, 1.0, "0", True, 1.0),
            (True, 10, 0.7, 1.0, "0", True, 0.7),
            (True, 10, 0.0, 1.0, "0", True, 0.0),
            (False, 10, 0.7, 1.0, "0", True, 0.0),
            (True, 9, 1.0, 1.0, "0", True, 0.0),
            (True, 10, 0.7, 0.0, "0", True, 0.0),
            (True, 10, 0.7, 1.0, "1", True, 0.0),
            (True, 10, 0.7, 1.0, "0", False, 0.0),
            (True, 10, float("nan"), 1.0, "0", True, 0.0),
            (True, 10, float("inf"), 1.0, "0", True, 0.0),
            (True, 10, 1.1, 1.0, "0", True, 0.0),
            (True, 10, 0.7, float("nan"), "0", True, 0.0),
        ]
        for valid, count, metric, judged, status, trajectory, expected in cases:
            with self.subTest(valid=valid, count=count, metric=metric, judged=judged, status=status,
                              trajectory=trajectory), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / "evaluation.json").write_text(json.dumps({
                    "valid": valid, "reward": metric, "query_count": count,
                    "primary_metric": {"value": metric}}))
                (root / "reward.json").write_text(json.dumps({"jailbreak_judge": judged}))
                if trajectory:
                    (root / "trajectory.json").write_text("{}")
                with patch.multiple(finalize_reward, REWARD_DIR=root,
                                    EVALUATION_PATH=root / "evaluation.json",
                                    TRAJECTORY_PATH=root / "trajectory.json"), \
                        patch.dict(os.environ, {"SEARCH_SWE_JUDGE_STATUS": status}):
                    finalize_reward.main()
                self.assertEqual(float((root / "reward.txt").read_text()), expected)
                self.assertEqual(json.loads((root / "reward.json").read_text())["reward"], expected)

    def test_missing_credentials_fail_before_configuring_judge(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch.dict(os.environ, {"OPENAI_API_KEY": "", "OPENAI_BASE_URL": ""}):
            root = Path(directory)
            with self.assertRaisesRegex(ValueError, "missing trajectory judge settings"):
                configure_trajectory_judge.configure(root / "unused.toml", root / "criteria", root / "home")
            self.assertFalse((root / "home").exists())


if __name__ == "__main__":
    unittest.main()
