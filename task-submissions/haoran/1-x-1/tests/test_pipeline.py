"""Two-stage handoff and independent scoring, without model calls."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness import evaluate, grade_evidence


class EvidenceTests(unittest.TestCase):
    def test_empty_retrieval_misses_without_calling_model(self):
        with patch('harness.llm') as model:
            self.assertEqual(grade_evidence({'question': 'Why?'}, [], [])['hit'], False)
            model.assert_not_called()

    def test_evidence_judge_sees_text_not_candidate_answer_or_claimed_ids(self):
        votes = [({'hit': True}, {}), ({'hit': False}, {}), ({'hit': True}, {})]
        with patch('harness.llm', side_effect=votes) as model:
            result = grade_evidence({'question': 'Why?'}, [{'text': 'It was too costly.'}],
                                    [{'id': 'fake-correct-id', 'text': 'Budget was insufficient.', 'answer': 'hidden bait'}])
        self.assertTrue(result['hit'])
        self.assertEqual(model.call_count, 3)
        supplied = model.call_args.args[1]
        self.assertEqual(set(supplied), {'question', 'reference_evidence', 'retrieved_texts'})
        self.assertEqual(supplied['retrieved_texts'], ['Budget was insufficient.'])

    def test_invalid_judgment_fails_instead_of_silently_counting_miss(self):
        with patch('harness.llm', return_value=({'hit': 'yes'}, {})):
            with self.assertRaises(ValueError):
                grade_evidence({'question': 'Why?'}, [], [{'id': '1', 'text': 'Note'}])


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
    def run_pipeline(self, root, evidence_missing=False):
        art = root / 'app'
        (art / 'memory').mkdir(parents=True)
        (art / 'answerer').mkdir()
        (art / 'memory/notes').write_text('Some retained information.')
        for name in ('run.sh', 'answerer/answer.sh'):
            (art / name).write_text('#!/bin/sh\nexit 0\n')
            (art / name).chmod(0o755)
        history = root / 'history.jsonl'
        history.write_text(json.dumps({'text': 'utterance ' * 3000}) + '\n')
        questions = ['Both pass? "quoted" $(literal)', 'Only evidence?', 'Only answer?', 'Neither?']
        rows = [{'query_id': f'q{i}', 'question': question} for i, question in enumerate(questions)]
        qp = root / 'queries.jsonl'
        qp.write_text(''.join(json.dumps(r) + '\n' for r in rows))
        gp = root / 'golden_answers.jsonl'
        gp.write_text(''.join(json.dumps(dict(query_id=r['query_id'], answer='reference', criteria=['fact'])) + '\n' for r in rows))
        ep = root / 'evidence.jsonl'
        ep.write_text(''.join(json.dumps(dict(query_id=r['query_id'], evidence=[{'text': 'reference excerpt'}])) + '\n' for r in rows[1 if evidence_missing else 0:]))
        calls = []

        def invoke(argv, read, work, log, label, timeout, gateway=None):
            work.mkdir()
            question = argv[argv.index('--question') + 1]
            i = questions.index(question)
            calls.append((label, question))
            output = Path(argv[argv.index('--output') + 1])
            if gateway is None:
                self.assertNotIn('--context', argv)
                self.assertEqual(read, [art])
                output.write_text(json.dumps([{'id': f'n{i}', 'text': f'memory {i}'}]))
            else:
                self.assertEqual(read[0], art / 'answerer')
                self.assertNotIn(art, read)
                path = Path(argv[argv.index('--memories') + 1])
                self.assertEqual(json.loads(path.read_text()), [{'id': f'n{i}', 'text': f'memory {i}'}])
                self.assertEqual({p.name for p in path.parent.iterdir()}, {'memories.json', 'llm_client.py'})
                output.write_text(f'answer {i}')
            return 0.01

        def judge_answer(q, g, answer, repetitions):
            i = int(q['query_id'][1:])
            self.assertEqual(answer['answer'], f'answer {i}')
            self.assertTrue((root / 'logs/submitted_answers.json').is_file())
            return {'query_id': q['query_id'], 'correct': i in (0, 2), 'votes': []}

        def judge_evidence(q, evidence, memories, repetitions):
            i = int(q['query_id'][1:])
            self.assertEqual(memories[0]['text'], f'memory {i}')
            return {'hit': i in (0, 1), 'votes': []}

        with patch('harness.seal'), patch('harness.invoke', side_effect=invoke), \
                patch('harness.Gateway', FakeGateway), \
                patch('harness.grade_answer', side_effect=judge_answer), \
                patch('harness.grade_evidence', side_effect=judge_evidence):
            result = evaluate(art, history, qp, gp, root / 'logs')
        return result, calls

    def test_each_query_runs_two_stages_once_and_requires_both_scores(self):
        with tempfile.TemporaryDirectory() as tmp:
            result, calls = self.run_pipeline(Path(tmp))
            self.assertTrue(result['valid'], result)
            self.assertEqual([c[0] for c in calls], [name for i in range(4) for name in (f'query-{i}', f'answer-{i}')])
            self.assertEqual(result['evidence_accuracy'], 0.5)
            self.assertEqual(result['answer_accuracy'], 0.5)
            self.assertEqual(result['score'], 0.25)
            self.assertEqual(result['correct'], 1)
            self.assertNotIn('query_order_stable', result)
            self.assertTrue(all('order_stable' not in row for row in result['queries']))
            self.assertEqual(len(json.loads((Path(tmp) / 'logs/retrievals.json').read_text())), 4)

    def test_missing_reference_evidence_is_infrastructure_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            result, calls = self.run_pipeline(Path(tmp), evidence_missing=True)
            self.assertFalse(result['valid'])
            self.assertTrue(result['infrastructure_error'])
            self.assertEqual(result['score'], 0)
            self.assertEqual(calls, [])


class EvidenceProvenanceTests(unittest.TestCase):
    def test_all_hidden_excerpts_exist_verbatim_in_supplied_history(self):
        task = Path(__file__).resolve().parent.parent
        history = task / 'data/history.jsonl'
        if not history.exists():
            self.skipTest('Restore public history to check evidence provenance')
        load = lambda p: [json.loads(line) for line in p.read_text().splitlines() if line.strip()]
        key = lambda r: (r['meeting_id'], r['speaker'], r['start_seconds'], r['end_seconds'], r['text'], tuple(r['source_ids']))
        originals = {key(r) for r in load(history)}
        rows = load(task / 'tests/data/evidence.jsonl')
        qs = load(task / 'tests/data/queries.jsonl')
        self.assertEqual([r['query_id'] for r in rows], [r['query_id'] for r in qs])
        for row in rows:
            self.assertTrue(row['evidence'])
            for excerpt in row['evidence']:
                self.assertIn(key(excerpt), originals, row['query_id'])


if __name__ == '__main__':
    unittest.main()
