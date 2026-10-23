"""Small synthetic fixtures exercise contracts, not full-data feasibility."""
import importlib.util
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import numpy as np

from finalize import finalize
from metrics import KS, dataset_score, recall, error_gain, missing_neighbors
from process import Process

TASK = Path(__file__).resolve().parents[1]


class CalibrationTests(unittest.TestCase):
    def test_truth_from_different_faiss_build_is_rejected(self):
        from kernel import kernel_signature, require_truth_kernel
        with tempfile.TemporaryDirectory() as directory:
            private = Path(directory)
            manifest = private / "truth-manifest.json"
            signature = kernel_signature()
            manifest.write_text(json.dumps({"runtime_signature": signature}))
            require_truth_kernel(private)
            manifest.write_text(json.dumps({"runtime_signature": {
                **signature, "binary_sha256": "different-build-of-the-same-version"}}))
            with self.assertRaisesRegex(RuntimeError, "different Faiss runtime"):
                require_truth_kernel(private)
            manifest.write_text(json.dumps({"faiss_version": signature["faiss_version"]}))
            with self.assertRaisesRegex(RuntimeError, "different Faiss runtime"):
                require_truth_kernel(private)

    def test_runtime_limits_and_invalid_values(self):
        import grader
        from kernel import kernel_signature
        with tempfile.TemporaryDirectory() as directory:
            public = Path(directory) / "public"
            public.mkdir()
            reference = Path(directory) / "reference"
            reference.mkdir()
            for name in ("exact_search.py", "baseline_search.py"):
                (reference / name).write_bytes((TASK / "environment" / name).read_bytes())
            calibration = {"timing_policy": "same-environment-exact-reference",
                           "exact_scan_fraction": grader.EXACT_SCAN_FRACTION,
                           "minimum_baseline_missing_neighbors": grader.MIN_BASELINE_MISSES,
                           "scoring_policy": "log-missed-neighbor-gain-over-public-reference",
                           "total_requested_neighbors": 25_000_000,
                           "cpu_affinity": list(range(16)), "runtime_signature": kernel_signature(),
                           "exact_reference_sha256": hashlib.sha256((reference / "exact_search.py").read_bytes()).hexdigest(),
                           "baseline": {"public_sha256": hashlib.sha256((reference / "baseline_search.py").read_bytes()).hexdigest()},
                           "datasets": {str(d): {"build_seconds": 60, "insert_seconds": 10,
                             "baseline_micro_recall": .8,
                             "baseline_missing_neighbors": 5_000_000,
                             "full_scan_seconds": [[20] * 5 for _ in range(10)]}
                             for d in (1536, 3072)}}
            def load():
                with patch.object(grader, "LIMITS", calibration):
                    return grader.load_limits()
            with patch.object(grader, "PUBLIC", public), patch.object(
                    grader.os, "sched_getaffinity", return_value=set(range(16))):
                self.assertEqual(load(), calibration)
                for invalid_fraction in (None, True, 0, .05, .99, float("nan")):
                    with self.subTest(fraction=invalid_fraction):
                        calibration["exact_scan_fraction"] = invalid_fraction
                        with self.assertRaisesRegex(RuntimeError, "Frozen query fraction"):
                            load()
                calibration["exact_scan_fraction"] = grader.EXACT_SCAN_FRACTION
                strong = calibration["datasets"]["1536"]
                original_anchor = strong.copy()
                strong.update(baseline_missing_neighbors=grader.MIN_BASELINE_MISSES,
                              baseline_micro_recall=1 - grader.MIN_BASELINE_MISSES / 25_000_000)
                self.assertEqual(load(), calibration)
                strong.update(baseline_missing_neighbors=grader.MIN_BASELINE_MISSES - 1,
                              baseline_micro_recall=1 - (grader.MIN_BASELINE_MISSES - 1) / 25_000_000)
                with self.assertRaisesRegex(RuntimeError, f"at least {grader.MIN_BASELINE_MISSES} neighbors"):
                    load()
                strong.update(original_anchor)
                (reference / "baseline_search.py").write_text("changed after calibration")
                with self.assertRaisesRegex(RuntimeError, "Public reference changed"):
                    load()
                (reference / "baseline_search.py").write_bytes((TASK / "environment/baseline_search.py").read_bytes())
                calibration["cpu_affinity"] = [0] * 16
                with self.assertRaisesRegex(RuntimeError, "16 allocated logical CPUs"):
                    load()
                calibration["cpu_affinity"] = list(range(1, 17))
                with self.assertRaisesRegex(RuntimeError, "CPUs are unavailable"):
                    load()
                calibration["cpu_affinity"] = list(range(16))
                calibration["runtime_signature"] = {}
                with self.assertRaisesRegex(RuntimeError, "different Faiss runtime"):
                    load()
                calibration["runtime_signature"] = kernel_signature()
                calibration["datasets"]["1536"]["build_seconds"] = float("nan")
                with self.assertRaisesRegex(RuntimeError, "preparation budgets"):
                    load()


class MetricsTests(unittest.TestCase):
    def test_each_missed_neighbor_counts_once_at_every_k(self):
        small, large = [0] * 101, [0] * 1001
        small[99] = 1
        large[990] = 1
        self.assertEqual(missing_neighbors([{"k": 100, "recall_histogram": small}]), 1)
        self.assertEqual(missing_neighbors([{"k": 1000, "recall_histogram": large}]), 10)
        large[990], large[999] = 0, 1
        self.assertEqual(missing_neighbors([{"k": 1000, "recall_histogram": large}]), 1)
        small[99], small[0] = 0, 1
        self.assertEqual(missing_neighbors([{"k": 100, "recall_histogram": small}]), 100)

    def test_public_baseline_anchor_and_full_recall(self):
        self.assertEqual(error_gain(99, 99), 0)
        self.assertEqual(error_gain(199, 99), 0)
        self.assertAlmostEqual(error_gain(9, 99), .5)
        self.assertEqual(error_gain(0, 99), 1)
        for baseline in (0, float("nan"), -1, True):
            with self.assertRaises(ValueError):
                error_gain(9, baseline)

    def test_partial_duplicate_unknown_and_nonfinite(self):
        row = {"ids": [1, 1, 2, 999, 3], "distances": [1, 1, 2, 0, float("nan")]}
        self.assertEqual(recall(row, [1, 2, 3, 4, 5], 5, 10), .4)
        self.assertEqual(recall({"ids": [True], "distances": [1]}, [1], 1, 10), 0)
        self.assertEqual(recall({"ids": [], "distances": []}, [1], 1, 10), 0)
        self.assertEqual(recall({"ids": [1], "distances": [10 ** 400]}, [1], 1, 10), 0)

    def test_exact_boundary_ties_are_valid_neighbors(self):
        from grader import boundary_ties
        initial = np.array([[0, 0], [1, 0], [-1, 0], [2, 0]], dtype="float32")
        query = np.array([0, 0], dtype="float32")
        response = {"ids": [0, 2], "distances": [0, 1]}
        ties = boundary_ties(response, [0, 1], np.float32(1), query,
                             initial, np.empty((0, 2), dtype="float32"), 4)
        self.assertEqual(ties, {2})
        self.assertEqual(recall(response, [0, 1], 2, 4, ties), 1)
        response["ids"] = [0, 3]
        ties = boundary_ties(response, [0, 1], np.float32(1), query,
                             initial, np.empty((0, 2), dtype="float32"), 4)
        self.assertEqual(ties, set())

    def test_excess_and_malformed(self):
        for row in (None, {}, [], {"ids": [1, 2], "distances": [1, 2]},
                    {"ids": [1], "distances": []}):
            self.assertEqual(recall(row, [1], 1, 10), 0)

    def cells(self):
        return [{"stage": stage, "k": k, "seconds": .1, "budget_seconds": 1,
                 "recall": .8} for stage in range(10) for k in KS]

    def test_stage_and_k_budgets_cannot_be_pooled(self):
        rows = self.cells()
        self.assertAlmostEqual(dataset_score(rows), .8)
        rows[23]["seconds"] = 1.001
        self.assertEqual(dataset_score(rows), 0)

    def test_missing_duplicate_and_nonfinite_cells(self):
        rows = self.cells()
        self.assertEqual(dataset_score(rows[:-1]), 0)
        self.assertEqual(dataset_score(rows[:-1] + [rows[0]]), 0)
        rows[0]["seconds"] = float("nan")
        self.assertEqual(dataset_score(rows), 0)

    def test_failed_audit_is_not_valid_zero_quality(self):
        evaluation = {"valid": True, "raw_reward": .73}
        for status, present, audit in [("1", True, {"integrity_judge": 1}),
                                        ("0", False, {"integrity_judge": 1}), ("0", True, {}),
                                        ("0", True, {"integrity_judge": True}),
                                        ("0", True, {"integrity": 1})]:
            result, healthy = finalize(evaluation, audit, status, present)
            self.assertEqual(result["reward"], 0)
            self.assertFalse(healthy)
        result, healthy = finalize(evaluation, {"integrity_judge": 0.0}, "0", True)
        self.assertTrue(healthy)
        self.assertEqual(result["reward"], 0)
        result, healthy = finalize(evaluation, {"integrity_judge": 1.0}, "0", True)
        self.assertTrue(healthy)
        self.assertEqual(result["reward"], .73)


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.directory = Path(self.tmp.name)
        self.workers = []

    def tearDown(self):
        for worker in self.workers:
            worker.close()
        self.tmp.cleanup()

    def start(self, code):
        worker = Process([sys.executable, "-u", "-c", code], self.directory, dict(os.environ),
                         self.directory / f"stderr-{len(self.workers)}.log")
        self.workers.append(worker)
        return worker

    def test_malformed_response_is_query_zero(self):
        worker = self.start("import sys\nfor line in sys.stdin: print('not-json', flush=True)")
        self.assertIsNone(worker.request({"op": "search"}, time.monotonic() + 5))

    def test_response_timeout(self):
        worker = self.start("import time; time.sleep(30)")
        with self.assertRaises(TimeoutError):
            worker.request({}, time.monotonic() + .1)

    def test_blocked_request_write_is_bounded(self):
        worker = self.start("import time; time.sleep(30)")
        with self.assertRaises(TimeoutError):
            worker.request({"padding": "x" * 1_000_000}, time.monotonic() + .1)

    def test_oversized_output(self):
        worker = self.start("import sys; sys.stdin.readline(); print('x'*200000, flush=True)")
        with self.assertRaises(ValueError):
            worker.request({}, time.monotonic() + 5)

    def test_exit_without_response(self):
        worker = self.start("import sys; sys.stdin.readline()")
        with self.assertRaises(ValueError):
            worker.request({}, time.monotonic() + 5)

    def test_exact_reference_preserves_insertions_and_supports_every_k(self):
        rng = np.random.default_rng(7)
        base = rng.normal(size=(1100, 16)).astype("float32")
        insertion = rng.normal(size=(100, 16)).astype("float32")
        query = insertion[9]
        np.save(self.directory / "initial.npy", base)
        np.save(self.directory / "insert.npy", insertion)
        worker = Process([sys.executable, str(TASK / "environment/exact_search.py")],
            self.directory, {**os.environ, "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1"},
            self.directory / "reference.stderr")
        self.workers.append(worker)
        deadline = time.monotonic() + 20
        self.assertEqual(worker.request({"op": "build", "vectors": str(self.directory / "initial.npy")}, deadline), {"ok": True})
        self.assertEqual(worker.request({"op": "insert", "vectors": str(self.directory / "insert.npy")}, deadline), {"ok": True})
        corpus = np.concatenate([base, insertion])
        squared = np.sum((corpus.astype("float64") - query.astype("float64")) ** 2, axis=1)
        truth = np.argsort(squared)
        for k in KS:
            response = worker.request({"op": "search", "vector": query.tolist(), "k": k}, deadline)
            self.assertEqual(response["ids"][0], 1109)
            self.assertEqual(recall(response, truth, k, 1200), 1)
            np.testing.assert_allclose(response["distances"], np.sqrt(squared[response["ids"]]), rtol=2e-6, atol=1e-6)


class SplitTests(unittest.TestCase):
    def test_no_overlap_and_all_rows_covered(self):
        spec = importlib.util.spec_from_file_location("prepare_data", TASK / "prepare_data.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        parts = module.split_rows(120, 100, 2, 5)
        self.assertEqual([len(p) for p in parts], [100, 10, 10])
        self.assertEqual(len(set(np.concatenate(parts).tolist())), 120)
        for first, second in zip(parts, module.split_rows(120, 100, 2, 5)):
            np.testing.assert_array_equal(first, second)


if __name__ == "__main__":
    unittest.main()
