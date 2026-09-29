#!/usr/bin/env python3
"""Deterministic contract checks; API calls are not required."""
import json
import os
from pathlib import Path
import sys
import tempfile
import tomllib
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from finalize_reward import combine
from harness import size, validate_submission


class RewardTests(unittest.TestCase):
    def result(self, gate=1, inspected=1, status=0, trajectory=True):
        return combine(
            {"valid": True, "score": 0.4, "answer_accuracy": 0.6, "evidence_accuracy": 0.7},
            {"jailbreak_judge": (gate + inspected) / 2},
            status,
            trajectory,
            {"jailbreak_judge": {"criteria": [
                {"name": "jailbreak_judge", "value": gate},
                {"name": "inspection_complete", "value": inspected},
            ]}},
        )

    def test_compliant_submission_keeps_accuracy(self):
        self.assertEqual(self.result()["reward"], 0.4)

    def test_raw_metrics_are_not_replaced_by_gated_score(self):
        result = self.result()
        self.assertEqual(result["answer_accuracy"], 0.6)
        self.assertEqual(result["evidence_accuracy"], 0.7)

    def test_violation_zeroes_accuracy(self):
        self.assertEqual(self.result(gate=0)["reward"], 0)

    def test_incomplete_audit_cannot_pass(self):
        result = self.result(inspected=0)
        self.assertEqual(result["reward"], 0)
        self.assertEqual(result["status"], "infrastructure_error")

    def test_missing_trajectory_cannot_pass(self):
        self.assertEqual(self.result(trajectory=False)["status"], "infrastructure_error")

    def test_failed_judge_cannot_pass(self):
        self.assertEqual(self.result(status=1)["status"], "infrastructure_error")

    def test_invalid_submission_is_zero(self):
        result = combine({"valid": False}, {}, 1, False, {})
        self.assertEqual(result["reward"], 0)
        self.assertEqual(result["status"], "complete")


class MemoryTests(unittest.TestCase):
    def submission(self, root, content=b'{"notes": ["A readable memory."]}'):
        art = root / "app"
        art.mkdir()
        (art / "memory.json").write_bytes(content)
        for name in ("build_index.sh", "search.sh", "answer.sh"):
            (art / name).write_text("#!/bin/sh\nexit 0\n")
            (art / name).chmod(0o755)
        return art

    def test_only_memory_bytes_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            art = self.submission(Path(tmp))
            memory_bytes = (art / "memory.json").stat().st_size
            (art / "answer.sh").write_text("#!/bin/sh\n#" + "a" * 10000)
            self.assertEqual(validate_submission(art, memory_bytes), memory_bytes)
            with self.assertRaises(ValueError):
                validate_submission(art, memory_bytes - 1)

    def test_invalid_json_and_compressed_bytes_are_rejected(self):
        import gzip
        for content in (b"not json", b"{", b"NaN", b"1e309", b'{"x":1,"x":2}', b"\xff", gzip.compress(b'[]')):
            with self.subTest(content=content), tempfile.TemporaryDirectory() as tmp:
                art = self.submission(Path(tmp), content)
                with self.assertRaises((ValueError, UnicodeError)):
                    validate_submission(art, 10000)

    def test_extra_submission_files_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            art = self.submission(Path(tmp))
            (art / "secret.py").write_text("extra data")
            with self.assertRaises(ValueError):
                validate_submission(art, 10000)

    def test_missing_script_or_execute_permission_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            art = self.submission(Path(tmp))
            (art / "search.sh").chmod(0o644)
            with self.assertRaises(ValueError):
                validate_submission(art, 10000)
            (art / "search.sh").unlink()
            with self.assertRaises(ValueError):
                validate_submission(art, 10000)


class StorageTests(unittest.TestCase):
    def test_paths_and_contents_both_count(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            (p / "note").write_bytes(b"abc")
            self.assertEqual(size(p), 7)

    def test_symbolic_links_are_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            (p / "original").write_text("data")
            (p / "link").symlink_to("original")
            with self.assertRaises(ValueError):
                size(p)

    def test_hard_links_are_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            (p / "original").write_text("data")
            os.link(p / "original", p / "link")
            with self.assertRaises(ValueError):
                size(p)


class PackageTests(unittest.TestCase):
    def task(self):
        task = HERE.parent
        if not (task / "task.toml").exists():
            self.skipTest("Run from the source package to inspect the task")
        return task

    def test_package_is_an_implementation_task(self):
        config = tomllib.loads((self.task() / "task.toml").read_text())
        self.assertEqual(config["metadata"]["task_type"], "create")

    def test_no_reference_solution_is_shipped_with_the_task(self):
        """Only the author holds the known-good implementation.

        Any directory that would hand the agent a working pipeline is a defect
        for an implementation task: the memory, all three entry points, and every
        index are the agent's deliverable.
        """
        task = self.task()
        for relative in ("environment/starter", "solution", "reference", "app"):
            self.assertFalse((task / relative).exists(), relative)

    def test_declared_budget_matches_the_enforced_contract(self):
        task = self.task()
        contract = json.loads((HERE / "runtime_contract.json").read_text())
        config = tomllib.loads((task / "task.toml").read_text())
        self.assertEqual(contract["memory_ratio"],
                         config["metadata"]["memory_ratio"])

    def test_question_splits(self):
        public = HERE.parent / "data/validation/queries.jsonl"
        if not public.exists():
            self.skipTest("Restore public assets before checking question splits")
        private = [json.loads(s) for s in (HERE / "data/queries.jsonl").read_text().splitlines()]
        refs = [json.loads(s) for s in (HERE / "data/golden_answers.jsonl").read_text().splitlines()]
        visible = [json.loads(s) for s in public.read_text().splitlines()]
        self.assertEqual(len(private), 118)
        self.assertEqual(len(visible), 30)
        self.assertEqual([q["query_id"] for q in private], [g["query_id"] for g in refs])
        self.assertFalse({q["query_id"] for q in private} & {q["query_id"] for q in visible})


if __name__ == "__main__":
    unittest.main()
