"""Author-side tests for metric boundaries and externally measured search I/O."""

import json
import math
import os
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from fractions import Fraction
from pathlib import Path
from statistics import median

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
from benchmark import SearchProcess, index_bytes, measure
from evaluate import InvalidSubmission, evaluate, quality_passes, tradeoff_reward, validate_response
from grader import copy_source, tree_bytes


def response(qid, ids):
    return {"query_id": qid, "results": [{"doc_id": str(d), "score": 20 - i}
                                        for i, d in enumerate(ids)]}


class QualityTests(unittest.TestCase):
    def setUp(self):
        self.queries = [{"query_id": "a", "text": "apple"}, {"query_id": "b", "text": "banana"}]
        self.qrels = {"a": {"2", "3"}, "b": {"4"}}

    def score(self, rows):
        return evaluate(rows, self.queries, self.qrels, document_count=12)

    def test_full_denominator_and_multiple_relevant(self):
        score = self.score([response("a", [0, 2, 3])])
        self.assertEqual(Fraction(score["mrr_numerator"], score["mrr_denominator"]), Fraction(1, 4))
        self.assertFalse(score["complete"])

    def test_exact_floor_not_rounded(self):
        ref = self.score([response("a", [2]), response("b", [0, 1, 4])])
        equal = self.score([response("b", [0, 1, 4]), response("a", [3])])
        lower = self.score([response("a", [2]), response("b", [0, 1, 2, 4])])
        self.assertTrue(quality_passes(equal, ref))
        self.assertFalse(quality_passes(lower, ref))
        rounded = {**ref, "mrr_numerator": 6666, "mrr_denominator": 10000}
        self.assertFalse(quality_passes(rounded, ref))

    def test_tenth_rank_counts(self):
        score = self.score([response("a", [0, 1, 4, 5, 6, 7, 8, 9, 10, 2]), response("b", [])])
        self.assertAlmostEqual(score["mrr_at_10"], .05)

    def test_bad_ids_and_scores(self):
        rows = [response("a", [1, 1]), response("a", [12]), response("a", list(range(11))),
                response("a", ["01"]), response("a", ["-1"])]
        rows.append(response("a", ["9" * 5000]))
        for score in [math.nan, math.inf, True, 10**1000]:
            rows.append({"query_id": "a", "results": [{"doc_id": "2", "score": score}]})
        rows.append({"query_id": "a", "results": [{"doc_id": "1", "score": 0},
                                                  {"doc_id": "2", "score": 1}]})
        for row in rows:
            with self.subTest(row=row), self.assertRaises(InvalidSubmission):
                validate_response(row, "a", document_count=12)

    def test_unknown_and_duplicate_queries(self):
        for rows in [[response("x", [])], [response("a", []), response("a", [])]]:
            with self.assertRaises(InvalidSubmission):
                self.score(rows)

    def test_tradeoff_gates_and_baseline(self):
        good = self.score([response("a", [2]), response("b", [4])])
        baseline = {"quality": good, "warm_seconds": 10, "index_bytes": 100}
        weights = {"quality": 1, "time": 1, "disk": 1}
        self.assertEqual(tradeoff_reward(baseline, baseline, weights), .5)
        fast = {**baseline, "warm_seconds": 1}
        self.assertGreater(tradeoff_reward(fast, baseline, weights), .5)
        incomplete = {**fast, "quality": self.score([response("a", [2])])}
        self.assertEqual(tradeoff_reward(incomplete, baseline, weights), 0)


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def worker(self, code):
        return [sys.executable, "-u", "-c", code]

    def test_successful_cold_and_warm(self):
        command = self.worker("import sys,json\nfor line in sys.stdin:\n q=json.loads(line); print(json.dumps({'query_id':q['query_id'],'results':[{'doc_id':'0','score':1.0}]}),flush=True)")
        queries = [{"query_id": str(i), "text": f"query {i}"} for i in range(3)]
        metrics, rows = measure(command, queries=queries, warmup=[{"query_id": "w", "text": "warmup"}],
                                directory=self.directory / "measurement", document_count=2,
                                cold_samples=2, timeout=3, batch_timeout=10)
        self.assertEqual(len(rows), 3)
        self.assertEqual(len(metrics["cold_start_to_first_result_seconds"]), 2)
        self.assertGreater(metrics["warm_seconds"], 0)
        self.assertAlmostEqual(metrics["warm_qps"] * metrics["warm_seconds"], 3)
        self.assertEqual(metrics["warm_repetitions"], 5)
        self.assertEqual(len(metrics["warm_seconds_samples"]), 5)
        self.assertEqual(metrics["warm_seconds"], median(metrics["warm_seconds_samples"]))
        self.assertEqual(len(list((self.directory / "measurement").glob("warm-*.stderr.log"))), 5)

    def test_complete_batch_median_is_not_the_mean_or_a_trimmed_mean(self):
        clock = [0.]
        durations = iter([1., 2., 3., 7., 30.])

        class Worker:
            def __init__(self, command, *, stderr, **kwargs):
                self.started = clock[0]
                self.peak_rss_kib = 1
                self.duration = next(durations) if stderr.name.startswith('warm-') else .1

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                pass

            def request(self, query, **kwargs):
                duration = .1 if query['query_id'] == 'w' else self.duration
                clock[0] += duration
                return response(query['query_id'], [0]), duration

        with patch('benchmark.SearchProcess', Worker), patch('benchmark.time.monotonic', side_effect=lambda: clock[0]):
            metrics, _ = measure(['fixture'], queries=[{'query_id': 'a', 'text': 'query'}],
                                 warmup=[{'query_id': 'w', 'text': 'warmup'}],
                                 directory=self.directory / 'median', document_count=2,
                                 cold_samples=1, timeout=60, batch_timeout=120)
        self.assertEqual(len(metrics['warm_seconds_samples']), 5)
        self.assertAlmostEqual(metrics['warm_seconds'], 3.)

    def test_later_warm_result_changes_are_rejected(self):
        counter = self.directory / "counter"
        code = ("import sys,json\nfrom pathlib import Path\n"
                f"p=Path({str(counter)!r})\n"
                "n=int(p.read_text())+1 if p.exists() else 1\np.write_text(str(n))\n"
                "for line in sys.stdin:\n"
                " q=json.loads(line); print(json.dumps({'query_id':q['query_id'],"
                "'results':[{'doc_id':'0','score':1 if n<6 else 2}]}),flush=True)\n")
        with self.assertRaisesRegex(InvalidSubmission, "Repeated warm"):
            measure(self.worker(code), queries=[{"query_id": "a", "text": "apple"}],
                    warmup=[{"query_id": "w", "text": "warmup"}],
                    directory=self.directory / "changing", document_count=2,
                    cold_samples=1, timeout=3, batch_timeout=10)

    def test_timeout_kills_worker(self):
        worker = SearchProcess(self.worker("import time; time.sleep(30)"), stderr=self.directory / "timeout.log")
        with self.assertRaises(TimeoutError):
            with worker:
                worker.request({"query_id": "a", "text": "x"}, timeout=.05, document_count=2)
        self.assertIsNotNone(worker.process.poll())

    def test_full_stdin_pipe_times_out(self):
        # Fill the pipe before a valid request. A blocking write used to hang
        # indefinitely even though the controller had a request deadline.
        worker = SearchProcess(self.worker("import time; time.sleep(30)"),
                               stderr=self.directory / "blocked-input.log")
        with self.assertRaises(TimeoutError), worker:
            while True:
                try:
                    os.write(worker.process.stdin.fileno(), b"x" * 4096)
                except BlockingIOError:
                    break
            worker.request({"query_id": "a", "text": "x"}, timeout=.05, document_count=2)

    def test_malformed_oversized_and_failure(self):
        for i, code in enumerate(["print('not JSON',flush=True)", "print('x'*70000,flush=True)", "raise SystemExit(1)"]):
            with self.subTest(code=code), self.assertRaises(InvalidSubmission):
                with SearchProcess(self.worker(code), stderr=self.directory / f"bad-{i}.log") as worker:
                    worker.request({"query_id": "a", "text": "x"}, timeout=3, document_count=2)

    def test_overlap_by_normalized_text(self):
        with self.assertRaisesRegex(ValueError, "disjoint"):
            measure([], queries=[{"query_id": "a", "text": " Apple   Pie "}],
                    warmup=[{"query_id": "b", "text": "apple pie"}], directory=self.directory / "bad",
                    document_count=2, cold_samples=1)

    def test_descendant_stdout_does_not_hang_shutdown(self):
        command = self.worker("import sys,json,subprocess\nsubprocess.Popen([sys.executable,'-c','import time; time.sleep(30)'])\nfor line in sys.stdin:\n q=json.loads(line); print(json.dumps({'query_id':q['query_id'],'results':[]}),flush=True)")
        started = time.monotonic()
        with SearchProcess(command, stderr=self.directory / "descendant.log") as worker:
            worker.request({"query_id": "a", "text": "x"}, timeout=3, document_count=2)
        self.assertLess(time.monotonic() - started, 3)

    def test_cold_warm_mismatch(self):
        command = self.worker("import sys,json\nn=0\nfor line in sys.stdin:\n n+=1; q=json.loads(line); print(json.dumps({'query_id':q['query_id'],'results':[{'doc_id':str(n%2),'score':1}]}),flush=True)")
        with self.assertRaisesRegex(InvalidSubmission, "disagree"):
            measure(command, queries=[{"query_id": "a", "text": "apple"}],
                    warmup=[{"query_id": "w", "text": "warmup"}], directory=self.directory / "mismatch",
                    document_count=2, cold_samples=1)

    def test_index_size_rejects_external_links(self):
        index = self.directory / "index"
        index.mkdir()
        (index / "postings").write_bytes(b"abc")
        self.assertEqual(index_bytes(index), 3)
        (index / "escape").symlink_to("/etc/passwd")
        with self.assertRaises(ValueError):
            index_bytes(index)
        (index / "escape").unlink()
        os.link(index / "postings", index / "duplicate")
        with self.assertRaises(ValueError):
            index_bytes(index)

    def test_workspace_monitor_allows_deleted_temporary_file(self):
        transient = self.directory / "temporary-object"
        transient.write_text("being renamed by compiler")
        def changing_walk(*args, **kwargs):
            transient.unlink()
            yield str(self.directory), [], [transient.name]
        with patch("grader.os.walk", changing_walk):
            self.assertEqual(tree_bytes(self.directory), 0)

    def test_index_size_rejects_xattrs_on_root_directories_and_files(self):
        index = self.directory / "index"
        index.mkdir()
        nested = index / "nested"
        nested.mkdir()
        postings = nested / "postings"
        postings.write_bytes(b"x")
        for path in [index, nested, postings]:
            with self.subTest(path=path):
                os.setxattr(path, "user.hidden-index", b"x" * 2048)
                try:
                    with self.assertRaisesRegex(ValueError, "extended attributes"):
                        index_bytes(index)
                finally:
                    os.removexattr(path, "user.hidden-index")
        self.assertEqual(index_bytes(index), 1)

    def test_index_xattr_check_fails_closed(self):
        (self.directory / "postings").write_bytes(b"x")
        with patch("benchmark.os.listxattr", side_effect=PermissionError("denied")):
            with self.assertRaises(PermissionError):
                index_bytes(self.directory)

    def test_workspace_monitor_rejects_excess_bytes(self):
        (self.directory / "oversized").write_bytes(b"123456")
        with self.assertRaises(InvalidSubmission):
            tree_bytes(self.directory, limit=5)

    def test_malformed_package_is_invalid_submission(self):
        source = self.directory / "source"
        source.mkdir()
        (source / "src").mkdir()
        (source / "src/main.rs").write_text("fn main() {}\n")
        (source / "Cargo.lock").write_text("version = 4\n")
        for package in ('[]', '"bm25-search"', 'true', '7'):
            (source / "Cargo.toml").write_text(f"package = {package}\n")
            with self.subTest(package=package), self.assertRaises(InvalidSubmission):
                copy_source(source)


if __name__ == "__main__":
    unittest.main()
