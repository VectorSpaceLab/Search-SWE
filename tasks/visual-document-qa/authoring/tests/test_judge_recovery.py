"""Offline interruption/recovery tests; no provider calls or submission execution."""

import sys
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(TASK_ROOT / "tests"))


import json
import multiprocessing
import os
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

import requests

import grader
import judge_recovery as recovery
from test_semantic_grading import job


class CheckpointTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.store = recovery.SampleStore(self.root, "fixture")

    def test_interruption_retains_successful_zero_and_resumes_missing_samples(self):
        with patch.object(grader, "llm", side_effect=[
            {"score": 0, "reason": "Wrong answer."}, recovery.TemporaryJudgeError("offline"),
        ]):
            with self.assertRaises(recovery.TemporaryJudgeError):
                grader.grade(job(), self.store)
        reopened = recovery.SampleStore(self.root, "fixture")
        with patch.object(grader, "llm", return_value={"score": 1, "reason": "Equivalent."}) as llm:
            row = grader.grade(job(), reopened)
        self.assertEqual(llm.call_count, 2)
        self.assertEqual([sample["value"] for sample in row["judge_samples"]], [0, 1, 1])
        self.assertAlmostEqual(row["value"], 2 / 3)
        with patch.object(grader, "llm") as llm:
            self.assertEqual(grader.grade(job(), reopened), row)
        llm.assert_not_called()
        self.assertEqual(len(list(reopened.root.glob("*.json"))), 3)

    def test_changed_answer_reference_or_context_cannot_reuse_samples(self):
        with patch.object(grader, "llm", return_value={"score": 1, "reason": "Equivalent."}):
            grader.grade(job(), self.store)
        cases = [
            (job(prediction="Different prediction"), self.store),
            (job(reference="Different reference"), self.store),
            (job(), recovery.SampleStore(self.root, "different-grading-context")),
        ]
        for sample, store in cases:
            with self.subTest(sample=sample, context=store.root.name):
                with patch.object(grader, "llm", return_value={"score": 0, "reason": "Different."}) as llm:
                    self.assertEqual(grader.grade(sample, store)["value"], 0)
                self.assertEqual(llm.call_count, 3)

    def test_process_exit_preserves_completed_sample_for_a_new_process(self):
        def interrupted_process():
            calls = 0

            def grade_once(sample):
                nonlocal calls
                calls += 1
                if calls == 2:
                    os._exit(17)
                return {"query_id": sample[0]["query_id"], "branch": sample[1]["branch"],
                        "value": 0., "error": None, "judge_reason": "Wrong."}

            with patch.object(grader, "grade_once", side_effect=grade_once):
                grader.grade(job(), self.store)

        process = multiprocessing.get_context("fork").Process(target=interrupted_process)
        process.start()
        process.join(timeout=5)
        if process.is_alive():
            process.kill()
            process.join()
            self.fail("Interrupted process did not exit")
        self.assertEqual(process.exitcode, 17)
        reopened = recovery.SampleStore(self.root, "fixture")
        with patch.object(grader, "llm", return_value={"score": 1, "reason": "Equivalent."}) as llm:
            self.assertAlmostEqual(grader.grade(job(), reopened)["value"], 2 / 3)
        self.assertEqual(llm.call_count, 2)

    def test_corrupt_sample_fails_instead_of_changing_the_score(self):
        with patch.object(grader, "llm", return_value={"score": 1, "reason": "Equivalent."}):
            grader.grade(job(), self.store)
        path = next(self.store.root.glob("*.json"))
        path.write_text('{"truncated":')
        with patch.object(grader, "llm") as llm:
            with self.assertRaises(recovery.PermanentJudgeError):
                grader.grade(job(), self.store)
        llm.assert_not_called()

    def test_interrupted_atomic_replace_preserves_previous_snapshot(self):
        path = self.root / "input.json"
        recovery.save_snapshot(path, "context", {"answer": "before"})
        with patch.object(recovery.os, "replace", side_effect=OSError("simulated interruption")):
            with self.assertRaises(OSError):
                recovery.save_snapshot(path, "context", {"answer": "after"})
        self.assertEqual(recovery.load_snapshot(path, "context"), {"answer": "before"})
        self.assertEqual(list(self.root.glob(".judge-*")), [])
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)


class RecoveryQueueTests(unittest.TestCase):
    def test_failed_question_is_retried_without_repeating_completed_samples(self):
        first = job()
        second = job()
        first[0]["query_id"] = "unstable"
        second[0]["query_id"] = "stable"
        counts = {"unstable": 0, "stable": 0}
        lock = threading.Lock()

        def grade_once(sample):
            query_id = sample[0]["query_id"]
            with lock:
                counts[query_id] += 1
                call = counts[query_id]
            if query_id == "unstable" and call == 2:
                raise recovery.TemporaryJudgeError("offline")
            return {"query_id": query_id, "branch": sample[1]["branch"], "value": 1.,
                    "error": None, "judge_reason": "Equivalent."}

        with tempfile.TemporaryDirectory() as temporary:
            store = recovery.SampleStore(temporary, "context")
            state = recovery.Recovery(time.monotonic() + 5)
            with patch.object(state, "pause"), patch.object(grader, "grade_once", side_effect=grade_once):
                rows = list(grader.grade_jobs([first, second], 2, store, state))
            self.assertEqual([row["query_id"] for row in rows], ["unstable", "stable"])
            self.assertEqual([row["value"] for row in rows], [1, 1])
            self.assertEqual(counts, {"unstable": 4, "stable": 3})
            self.assertEqual(state.deferred_jobs, 1)
            self.assertEqual(len(list(store.root.glob("*.json"))), 6)

    def test_three_transport_failures_recover_instead_of_aborting_evaluation(self):
        response = Mock(status_code=200)
        response.json.return_value = {"choices": [{"message": {
            "content": '{"score":1,"reason":"Equivalent."}'}}]}
        state = recovery.Recovery(time.monotonic() + 5)
        with tempfile.TemporaryDirectory() as temporary, \
                patch.dict(grader.os.environ, {"OPENAI_BASE_URL": "https://openrouter.ai/api/v1",
                                               "OPENAI_API_KEY": "offline-placeholder"}, clear=True), \
                patch.object(grader, "RECOVERY", state), patch.object(state, "pause"), \
                patch.object(grader.requests, "post", side_effect=[
                    requests.ConnectionError("private transport details") for _ in range(3)
                ] + [response] * 3) as post:
            rows = list(grader.grade_jobs([job()], 1, recovery.SampleStore(temporary, "context"), state))
        self.assertEqual(rows[0]["value"], 1)
        self.assertEqual(post.call_count, 6)
        self.assertEqual(state.deferred_jobs, 1)

    def test_permanent_error_does_not_launch_the_remaining_queue(self):
        state = recovery.Recovery(time.monotonic() + 5)
        with patch.object(grader, "grade", side_effect=recovery.PermanentJudgeError("HTTP 401")) as grade:
            with self.assertRaises(recovery.PermanentJudgeError):
                list(grader.grade_jobs(list(range(100)), 1, recovery=state))
        grade.assert_called_once_with(0)

    def test_deadline_stops_recovery_without_fabricating_results(self):
        state = recovery.Recovery(time.monotonic() - 1)
        with patch.object(grader, "grade") as grade:
            with self.assertRaises(recovery.JudgeDeadlineError):
                list(grader.grade_jobs([job()], 1, recovery=state))
        grade.assert_not_called()

    def test_server_cooldown_cannot_extend_the_overall_deadline(self):
        state = recovery.Recovery(time.monotonic() + 0.02)
        state.pause(301)
        with self.assertRaises(recovery.JudgeDeadlineError):
            state.wait()

    def test_cooldown_is_shared_and_cancellation_releases_waiters(self):
        state = recovery.Recovery(time.monotonic() + 5)
        state.pause(301)
        entered = threading.Event()
        finished = threading.Event()

        def wait():
            entered.set()
            with self.assertRaises(recovery.JudgeDeadlineError):
                state.wait()
            finished.set()

        thread = threading.Thread(target=wait)
        thread.start()
        self.assertTrue(entered.wait(1))
        self.assertFalse(finished.is_set())
        state.cancelled.set()
        thread.join(timeout=1)
        self.assertTrue(finished.is_set())


class ResumeIntegrationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.log = Path(temporary.name)
        self.jobs = [job(), job(branch="FinRAGBench-V")]
        for index, sample in enumerate(self.jobs):
            sample[0].update(query_id=str(index), doc_id="document")
            sample[1]["query_id"] = str(index)
        self.queries = [sample[0] for sample in self.jobs]
        self.labels = [sample[1] for sample in self.jobs]
        self.docs = [{"doc_id": "document", "page_count": 3}]
        for patcher in (
            patch.object(grader, "LOG", self.log),
            patch.object(grader, "stop"),
            patch.dict(grader.os.environ, {"OPENAI_BASE_URL": "https://openrouter.ai/api/v1",
                                          "OPENAI_API_KEY": "offline-placeholder",
                                          "JUDGE_MAX_CONCURRENCY": "1"}, clear=True),
            patch.object(grader, "read_jsonl", side_effect=lambda path: {
                "/tests/data/queries.jsonl": self.queries,
                "/tests/data/labels.jsonl": self.labels,
                "/task/data/corpus/records.jsonl": self.docs,
            }[path]),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_resume_skips_submission_and_only_grades_missing_samples(self):
        with patch.object(grader, "prepare_submission", return_value=([], self.jobs)), \
                patch.object(grader, "llm", side_effect=[
                    {"score": 0, "reason": "Wrong."}, recovery.PermanentJudgeError("HTTP 401")]):
            self.assertEqual(grader.main(), 1)
        failed = json.loads((self.log / "evaluation.json").read_text())
        self.assertFalse(failed["valid"])
        self.assertFalse(failed["answer_judge_succeeded"])
        self.assertEqual(failed["saved_judge_samples"], 1)
        self.assertTrue(failed["resume_available"])

        def success(system, payload, kind):
            return {"score": 1, "reason": "Equivalent."} if kind == "semantic" else 1.

        with patch.object(grader, "prepare_submission") as prepare, \
                patch.object(grader, "llm", side_effect=success) as llm:
            self.assertEqual(grader.main(resume_judging=True), 0)
        prepare.assert_not_called()
        self.assertEqual(llm.call_count, 5)
        result = json.loads((self.log / "evaluation.json").read_text())
        self.assertTrue(result["valid"])
        self.assertTrue(result["resumed_judging"])
        self.assertEqual(result["query_count"], 2)
        self.assertEqual(result["saved_judge_samples"], 6)
        self.assertAlmostEqual(result["primary_metric"]["value"], 5 / 6)
        with patch.object(grader, "prepare_submission") as prepare, patch.object(grader, "llm") as llm:
            self.assertEqual(grader.main(resume_judging=True), 0)
        prepare.assert_not_called()
        llm.assert_not_called()

    def test_resume_rejects_a_changed_model(self):
        with patch.object(grader, "prepare_submission", return_value=([], self.jobs)), \
                patch.object(grader, "llm", side_effect=recovery.PermanentJudgeError("HTTP 401")):
            self.assertEqual(grader.main(), 1)
        with patch.dict(grader.os.environ, {"DOCUMENT_JUDGE_MODEL": "different/model"}), \
                patch.object(grader, "prepare_submission") as prepare, patch.object(grader, "llm") as llm:
            self.assertEqual(grader.main(resume_judging=True), 1)
        prepare.assert_not_called()
        llm.assert_not_called()
        self.assertFalse(json.loads((self.log / "evaluation.json").read_text())["valid"])

    def test_new_run_clears_stale_success_before_submission_execution(self):
        (self.log / "evaluation.json").write_text(json.dumps({"valid": True, "answer_judge_succeeded": True}))

        def check_initial_state(*args):
            report = json.loads((self.log / "evaluation.json").read_text())
            self.assertFalse(report["valid"])
            self.assertFalse(report["answer_judge_succeeded"])
            raise RuntimeError("simulated interruption")

        with patch.object(grader, "prepare_submission", side_effect=check_initial_state):
            self.assertEqual(grader.main(), 1)

    def test_failed_new_run_cannot_resume_answers_from_an_older_evaluation(self):
        with patch.object(grader, "prepare_submission", return_value=([], self.jobs)), \
                patch.object(grader, "llm", side_effect=recovery.PermanentJudgeError("HTTP 401")):
            self.assertEqual(grader.main(), 1)
        with patch.object(grader, "prepare_submission", side_effect=RuntimeError("new build failed")):
            self.assertEqual(grader.main(), 1)
        with patch.object(grader, "prepare_submission") as prepare, patch.object(grader, "llm") as llm:
            self.assertEqual(grader.main(resume_judging=True), 1)
        prepare.assert_not_called()
        llm.assert_not_called()
        report = json.loads((self.log / "evaluation.json").read_text())
        self.assertFalse(report["valid"])
        self.assertIn("current evaluation", report["errors"][-1])


if __name__ == "__main__":
    unittest.main()
