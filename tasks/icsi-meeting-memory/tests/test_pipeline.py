"""Index construction, stage handoff and independent scoring, without model calls."""

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness import (
    evaluate,
    grade_evidence,
    validate_evidence_judgment,
    validate_retrieval_citations,
    anchor_retrieval_citations,
)


class JudgeLogTests(unittest.TestCase):
    def setUp(self):
        self.logdir = tempfile.TemporaryDirectory()
        self.env = patch.dict(
            "os.environ",
            {"ICSI_JUDGE_USAGE_PATH": str(Path(self.logdir.name) / "usage.jsonl")},
        )
        self.env.start()
        self.addCleanup(self.env.stop)
        self.addCleanup(self.logdir.cleanup)


class EvidenceTests(JudgeLogTests):
    def test_empty_retrieval_misses_without_calling_model(self):
        with patch("harness.llm") as model:
            self.assertEqual(grade_evidence({"question": "Why?"}, [], [])["hit"], False)
            model.assert_not_called()

    def test_extraction_never_sees_reference_or_candidate_answer(self):
        citation = {"memory_index": 0, "quote": "Budget was insufficient."}
        positive = {
            "hit": True,
            "matches": [{"passage_index": 0, "reference_fact": "Insufficient budget"}],
        }
        support = ({"supported": True}, {})
        outputs = [
            ({"citations": [citation]}, {}),
            (positive, {}),
            support,
            ({"hit": False, "matches": []}, {}),
            (positive, {}),
            support,
        ]
        with patch("harness.llm", side_effect=outputs) as model:
            result = grade_evidence(
                {"question": "Why?"},
                [{"text": "It was too costly."}],
                ["Budget was insufficient."],
            )
        self.assertAlmostEqual(result["hit"], 2 / 3)
        self.assertEqual(model.call_count, 6)
        self.assertEqual(
            set(model.call_args_list[0].args[1]), {"question", "retrieved_texts"}
        )
        self.assertEqual(
            model.call_args_list[0].args[1]["retrieved_texts"],
            [{"memory_index": 0, "text": "Budget was insufficient."}],
        )
        supplied = model.call_args_list[1].args[1]
        self.assertEqual(
            set(supplied), {"question", "reference_evidence", "retrieved_passages"}
        )
        self.assertEqual(
            supplied["retrieved_passages"],
            [{"passage_index": 0, "quote": citation["quote"]}],
        )
        self.assertEqual(result["votes"][0]["matched_passages"], [citation])
        audit = model.call_args_list[2].args[1]
        self.assertEqual(set(audit), {"question", "claims"})
        self.assertEqual(audit["claims"][0]["passage"], citation["quote"])
        self.assertEqual(audit["claims"][0]["source_text"], "Budget was insufficient.")
        self.assertEqual(set(audit["claims"][0]), {"fact", "passage", "source_text"})

    def test_comparison_indices_are_independent_from_source_memory_indices(self):
        citation = {"memory_index": 2, "quote": "The proposal was rejected."}
        positive = {
            "hit": True,
            "matches": [
                {"passage_index": 0, "reference_fact": "The proposal was rejected"}
            ],
        }
        with patch(
            "harness.llm",
            side_effect=[
                ({"citations": [citation]}, {}),
                (positive, {}),
                ({"supported": True}, {}),
            ],
        ) as model:
            result = grade_evidence(
                {"question": "What happened?"},
                [{"text": "The proposal was rejected."}],
                ["Other text.", "More text.", "The proposal was rejected."],
                repetitions=1,
            )
        self.assertTrue(result["hit"])
        passages = model.call_args_list[1].args[1]["retrieved_passages"]
        self.assertEqual(
            passages, [{"passage_index": 0, "quote": "The proposal was rejected."}]
        )
        self.assertNotIn("memory_index", passages[0])
        self.assertEqual(result["votes"][0]["matched_passages"][0]["memory_index"], 2)

    def test_unsupported_claim_cannot_earn_a_hit(self):
        for support in ({"supported": False},):
            outputs = [
                (
                    {
                        "citations": [
                            {
                                "memory_index": 0,
                                "quote": "An unnamed person discussed batteries.",
                            }
                        ]
                    },
                    {},
                ),
                (
                    {
                        "hit": True,
                        "matches": [
                            {
                                "passage_index": 0,
                                "reference_fact": "Mina discussed batteries.",
                            }
                        ],
                    },
                    {},
                ),
                (support, {}),
            ]
            with (
                self.subTest(support=support),
                patch("harness.llm", side_effect=outputs),
            ):
                result = grade_evidence(
                    {"question": "Who discussed batteries?"},
                    [{"text": "Mina discussed batteries."}],
                    ["An unnamed person discussed batteries."],
                    repetitions=1,
                )
            self.assertFalse(result["hit"])
            self.assertTrue(result["votes"][0]["judgment"]["hit"])

    def test_no_relevant_passages_miss_without_semantic_judge(self):
        with patch("harness.llm", return_value=({"citations": []}, {})) as model:
            result = grade_evidence(
                {"question": "Why?"},
                [{"text": "Because of cost."}],
                ["Unrelated text."],
            )
        self.assertFalse(result["hit"])
        self.assertEqual(model.call_count, 1)

    def test_invalid_judgment_fails_instead_of_silently_counting_miss(self):
        with patch("harness.llm", return_value=({"citations": "wrong"}, {})):
            with self.assertRaises(ValueError):
                grade_evidence({"question": "Why?"}, [], ["Note"])


class EvidenceCitationTests(JudgeLogTests):
    memories = [
        "Unrelated scheduling discussion.",
        "If the parameter is unknown, ask the user.",
    ]

    def extraction(self, **changes):
        citation = {"memory_index": 1, "quote": self.memories[1]}
        citation.update(changes)
        return {"citations": [citation]}

    def test_unique_exact_quote_repairs_wrong_item_number_only(self):
        judgment = self.extraction(memory_index=0)
        anchor_retrieval_citations(judgment, self.memories)
        self.assertEqual(
            judgment["citations"], [{"memory_index": 1, "quote": self.memories[1]}]
        )
        self.assertEqual(
            judgment["provenance_repairs"][0]["method"], "unique_exact_substring"
        )
        self.assertEqual(judgment["provenance_repairs"][0]["from_memory_index"], 0)
        validate_retrieval_citations(judgment, self.memories)

    def test_ambiguous_quote_cannot_repair_wrong_source(self):
        judgment = self.extraction(memory_index=0)
        with self.assertRaisesRegex(ValueError, "verbatim"):
            anchor_retrieval_citations(
                judgment, [self.memories[0], self.memories[1], self.memories[1]]
            )

    def test_reanchoring_never_fuzzy_matches_or_repairs_malformed_indices(self):
        for changes in (
            {"quote": "If the parameter is unknown ask the user."},
            {"quote": "If the parameter ... ask the user."},
            {"memory_index": True},
            {"memory_index": -1},
            {"memory_index": 2},
            {"quote": "A fact present only in the gold answer."},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                anchor_retrieval_citations(self.extraction(**changes), self.memories)

    def test_valid_repeated_quote_keeps_explicit_source(self):
        judgment = self.extraction()
        anchor_retrieval_citations(
            judgment, [self.memories[0], self.memories[1], self.memories[1]]
        )
        self.assertEqual(judgment["provenance_repairs"], [])
        self.assertEqual(judgment["citations"][0]["memory_index"], 1)

    def test_reference_only_quote_is_not_retrieved_evidence(self):
        with self.assertRaisesRegex(ValueError, "verbatim"):
            validate_retrieval_citations(
                self.extraction(
                    quote="The system asks the user when a parameter cannot be inferred."
                ),
                self.memories,
            )

    def test_wrong_item_out_of_range_bool_and_empty_quote_are_rejected(self):
        for changes in (
            {"memory_index": 0},
            {"memory_index": -1},
            {"memory_index": 2},
            {"memory_index": True},
            {"quote": ""},
            {"quote": " "},
            {"quote": "ask ... user"},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                validate_retrieval_citations(self.extraction(**changes), self.memories)

    def test_valid_contiguous_quote_can_use_different_wording_from_reference(self):
        validate_retrieval_citations(self.extraction(), self.memories)
        validate_evidence_judgment(
            {
                "hit": True,
                "matches": [
                    {
                        "passage_index": 0,
                        "reference_fact": "The system asks when it cannot infer a parameter.",
                    }
                ],
            },
            self.extraction()["citations"],
        )

    def test_missing_citations_invalid_indices_and_inconsistent_negative_are_rejected(
        self,
    ):
        for judgment in (
            {"hit": True},
            {"hit": True, "matches": []},
            {"hit": "yes", "matches": []},
            {
                "hit": True,
                "matches": [{"passage_index": True, "reference_fact": "fact"}],
            },
            {"hit": True, "matches": [{"passage_index": 1, "reference_fact": "fact"}]},
            {"hit": True, "matches": [{"passage_index": 0, "reference_fact": ""}]},
            {"hit": False, "matches": [{"passage_index": 0, "reference_fact": "fact"}]},
        ):
            with self.subTest(judgment=judgment), self.assertRaises(ValueError):
                validate_evidence_judgment(judgment, self.extraction()["citations"])

    def test_bad_citation_gets_one_repair_and_is_logged(self):
        bad = self.extraction(quote="not in retrieval")
        positive = {
            "hit": True,
            "matches": [{"passage_index": 0, "reference_fact": "Ask the user"}],
        }
        with patch(
            "harness.llm",
            side_effect=[
                (bad, {}),
                (self.extraction(), {}),
                (positive, {}),
                ({"supported": True}, {}),
            ],
        ) as model:
            result = grade_evidence(
                {"question": "What happens?"},
                [{"text": "Ask the user"}],
                self.memories,
                repetitions=1,
            )
        self.assertTrue(result["hit"])
        self.assertEqual(model.call_count, 4)
        self.assertEqual(len(result["extraction"]["rejected_attempts"]), 1)

    def test_repeated_bad_citations_are_judge_failure_not_a_score(self):
        with patch(
            "harness.llm", return_value=(self.extraction(quote="not present"), {})
        ) as model:
            with self.assertRaisesRegex(ValueError, "validation failed twice"):
                grade_evidence(
                    {"question": "What happens?"},
                    [{"text": "Ask the user"}],
                    self.memories,
                )
        self.assertEqual(model.call_count, 2)


class FakeGateway:
    class Error(RuntimeError):
        pass

    def __init__(self, key, limit, log, **kwargs):
        self.log = Path(log)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.log.write_text('{"calls": 0, "errors": []}')


class PipelineTests(unittest.TestCase):
    def run_pipeline(self, root, evidence_missing=False, mixed_votes=False):
        art = root / "app"
        art.mkdir()
        (art / "memory.json").write_text('["Some retained information."]')
        for name in ("build.sh", "run.sh", "answer.sh"):
            (art / name).write_text("#!/bin/sh\nexit 0\n")
            (art / name).chmod(0o755)
        history = root / "history.jsonl"
        history.write_text(json.dumps({"text": "utterance " * 3000}) + "\n")
        questions = [
            'Both pass? "quoted" $(literal)',
            "Only evidence?",
            "Only answer?",
            "Neither?",
        ]
        rows = [
            {"query_id": f"q{i}", "question": question}
            for i, question in enumerate(questions)
        ]
        qp = root / "queries.jsonl"
        qp.write_text("".join(json.dumps(r) + "\n" for r in rows))
        gp = root / "golden_answers.jsonl"
        gp.write_text(
            "".join(
                json.dumps(
                    dict(query_id=r["query_id"], answer="reference", criteria=["fact"])
                )
                + "\n"
                for r in rows
            )
        )
        ep = root / "evidence.jsonl"
        ep.write_text(
            "".join(
                json.dumps(
                    dict(
                        query_id=r["query_id"], evidence=[{"text": "reference excerpt"}]
                    )
                )
                + "\n"
                for r in rows[1 if evidence_missing else 0 :]
            )
        )
        calls = []

        def invoke(argv, read, work, log, label, timeout, gateway=None):
            work.mkdir()
            output = Path(argv[argv.index("--output") + 1])
            if label == "build":
                calls.append((label, None))
                self.assertEqual(read, [art / "build.sh", art / "memory.json"])
                output.mkdir()
                (output / "notes.json").write_text((art / "memory.json").read_text())
                return 0.01
            question = argv[argv.index("--question") + 1]
            i = questions.index(question)
            calls.append((label, question))
            if label.startswith("query-"):
                self.assertEqual(read[0], art / "run.sh")
                self.assertEqual(Path(argv[argv.index("--index") + 1]), read[1])
                self.assertTrue((read[1] / "notes.json").exists())
                self.assertNotIn(art / "memory.json", read)
                self.assertFalse((work.parent / "build").exists())
                output.write_text(json.dumps([f"memory {i}"]))
            else:
                self.assertEqual(read[0], art / "answer.sh")
                self.assertNotIn(art, read)
                path = Path(argv[argv.index("--memories") + 1])
                self.assertEqual(json.loads(path.read_text()), [f"memory {i}"])
                self.assertEqual(
                    {p.name for p in path.parent.iterdir()},
                    {"memories.json", "llm_client.py"},
                )
                self.assertEqual(path.parent.stat().st_mode & 0o777, 0o755)
                output.write_text(f"answer {i}")
            return 0.01

        def judge_answer(q, g, answer, repetitions):
            i = int(q["query_id"][1:])
            self.assertEqual(answer["answer"], f"answer {i}")
            self.assertTrue((root / "logs/submitted_answers.json").is_file())
            values = [True, False, True] if mixed_votes and i == 0 else [i in (0, 2)] * repetitions
            return {
                "query_id": q["query_id"],
                "correct": sum(values) / repetitions,
                "votes": [{"correct": value} for value in values],
            }

        def judge_evidence(q, evidence, memories, repetitions):
            i = int(q["query_id"][1:])
            self.assertEqual(memories[0], f"memory {i}")
            values = [True, True, False] if mixed_votes and i == 0 else [i in (0, 1)] * repetitions
            return {
                "hit": sum(values) / repetitions,
                "votes": [{"hit": value} for value in values],
            }

        with (
            patch("harness.seal"),
            patch("harness.invoke", side_effect=invoke),
            patch("harness.Gateway", FakeGateway),
            patch("harness.grade_answer", side_effect=judge_answer),
            patch("harness.grade_evidence", side_effect=judge_evidence),
        ):
            result = evaluate(art, history, qp, gp, root / "logs")
        return result, calls

    def test_each_query_runs_two_stages_once_and_requires_both_scores(self):
        with tempfile.TemporaryDirectory() as tmp:
            result, calls = self.run_pipeline(Path(tmp))
            self.assertTrue(result["valid"], result)
            self.assertEqual(
                [c[0] for c in calls],
                ["build"]
                + [name for i in range(4) for name in (f"query-{i}", f"answer-{i}")],
            )
            self.assertEqual(result["evidence_accuracy"], 0.5)
            self.assertEqual(result["answer_accuracy"], 0.5)
            self.assertEqual(result["score"], 0.25)
            self.assertEqual(result["correct"], 1)
            self.assertEqual(
                len(json.loads((Path(tmp) / "logs/retrievals.json").read_text())), 4
            )

    def test_fractional_joint_score_keeps_fixed_retrievals_and_answers(self):
        with tempfile.TemporaryDirectory() as tmp:
            result, calls = self.run_pipeline(Path(tmp), mixed_votes=True)
            self.assertTrue(result["valid"], result)
            self.assertAlmostEqual(result["queries"][0]["correct"], 1 / 3)
            self.assertAlmostEqual(result["score"], 1 / 12)
            self.assertAlmostEqual(result["evidence_accuracy"], 5 / 12)
            self.assertAlmostEqual(result["answer_accuracy"], 5 / 12)
            self.assertEqual(len(calls), 1 + 2 * 4)

    def test_answer_input_permissions_survive_production_umask(self):
        import os

        previous = os.umask(0o077)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                result, _ = self.run_pipeline(Path(tmp))
                self.assertTrue(result["valid"])
        finally:
            os.umask(previous)

    def test_missing_reference_evidence_is_infrastructure_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            result, calls = self.run_pipeline(Path(tmp), evidence_missing=True)
            self.assertFalse(result["valid"])
            self.assertTrue(result["infrastructure_error"])
            self.assertEqual(result["score"], 0)
            self.assertEqual(calls, [])


class EvidenceProvenanceTests(unittest.TestCase):
    def test_all_hidden_excerpts_exist_verbatim_in_supplied_history(self):
        task = Path(__file__).resolve().parent.parent
        history = task / "data/history.jsonl"
        if not history.exists():
            self.skipTest("Restore public history to check evidence provenance")
        load = lambda p: [
            json.loads(line) for line in p.read_text().splitlines() if line.strip()
        ]
        key = lambda r: (
            r["meeting_id"],
            r["speaker"],
            r["start_seconds"],
            r["end_seconds"],
            r["text"],
            tuple(r["source_ids"]),
        )
        originals = {key(r) for r in load(history)}
        rows = load(task / "tests/data/evidence.jsonl")
        qs = load(task / "tests/data/queries.jsonl")
        self.assertEqual([r["query_id"] for r in rows], [r["query_id"] for r in qs])
        for row in rows:
            self.assertTrue(row["evidence"])
            for excerpt in row["evidence"]:
                self.assertIn(key(excerpt), originals, row["query_id"])


if __name__ == "__main__":
    unittest.main()
