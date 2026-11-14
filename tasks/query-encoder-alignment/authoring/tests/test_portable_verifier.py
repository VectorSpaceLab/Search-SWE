"""Offline regressions for platform baselines and judge health."""

from contextlib import redirect_stdout
import importlib.metadata
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

TESTS = Path(__file__).resolve().parents[2] / 'tests'
sys.path.insert(0, str(TESTS))
import grader
import finalize_reward


class PlatformBaselineTests(unittest.TestCase):
    def grade(self, baseline_hits, *, changed_pin=None):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            corpus = root / 'corpus.jsonl'
            vectors = root / 'doc.npy'
            queries = root / 'queries.jsonl'
            labels = root / 'labels.jsonl'
            lock = root / 'lock.json'
            report = root / 'evaluation.json'
            run = root / 'run.sh'
            run.write_text('#!/bin/sh\nexit 0\n')
            run.chmod(0o755)

            def jsonl(path, rows):
                path.write_text(''.join(json.dumps(row) + '\n' for row in rows))

            jsonl(corpus, [{'id': 'a', 'text': 'first document'},
                           {'id': 'b', 'text': 'second document'}])
            np.save(vectors, np.zeros((2, 2560), dtype=np.float32))
            jsonl(queries, [{'query_id': f'q{i}', 'text': f'claim {i}'} for i in range(100)])
            jsonl(labels, [{'query_id': f'q{i}', 'relevant_doc_ids': ['a']} for i in range(100)])
            for name, hits in [('quality', baseline_hits), ('starter', 80), ('candidate', 73)]:
                jsonl(root / f'{name}.jsonl', [
                    {'query_id': f'q{i}', 'results': [{'doc_id': 'a' if i < hits else 'b', 'score': 1.0}]}
                    for i in range(100)])
            (root / 'starter-time').write_text('10')
            (root / 'candidate-time').write_text('5')
            definition = {
                'version': grader.QUALITY_VERSION,
                'corpus_sha256': grader.sha256(corpus),
                'vectors_sha256': grader.sha256(vectors),
                'queries_sha256': grader.sha256(queries),
                'labels_sha256': grader.sha256(labels),
                'implementation_sha256': grader.sha256(TESTS / 'quality_reference/baseline.py'),
                'retrieval_sha256': grader.sha256(TESTS / 'quality_reference/retrieval.py'),
            }
            if changed_pin:
                definition[changed_pin] = 'changed'
            lock.write_text(json.dumps(definition))
            env = {
                'SEARCH_SWE_STARTER_OUTPUT': str(root / 'starter.jsonl'),
                'SEARCH_SWE_CANDIDATE_OUTPUT': str(root / 'candidate.jsonl'),
                'SEARCH_SWE_QUALITY_OUTPUT': str(root / 'quality.jsonl'),
                'SEARCH_SWE_STARTER_TIME_FILE': str(root / 'starter-time'),
                'SEARCH_SWE_CANDIDATE_TIME_FILE': str(root / 'candidate-time'),
                'SEARCH_SWE_STARTER_REPORT': str(root / 'absent-report.json'),
            }
            def path(value):
                return run if str(value) == '/app/submission/run.sh' else Path(value)
            with patch.multiple(grader, CORPUS_PATH=corpus, VECTOR_PATH=vectors,
                                QUERIES_PATH=queries, GROUND_TRUTH_PATH=labels,
                                REPORT_PATH=report, BASELINE_LOCK=lock,
                                EXPECTED_CORPUS_SHA256=grader.sha256(corpus),
                                EXPECTED_VECTOR_SHA256=grader.sha256(vectors), Path=path), \
                    patch.dict(os.environ, env, clear=True), redirect_stdout(io.StringIO()):
                status = grader.main()
            return status, json.loads(report.read_text())

    def test_measured_baselines_and_predictions_can_differ_between_platforms(self):
        fingerprints = []
        for hits, expected in [(60, .325), (62, .28947368421052627)]:
            with self.subTest(baseline_hits=hits):
                status, report = self.grade(hits)
                self.assertEqual(status, 0)
                self.assertTrue(report['measurement_valid'])
                self.assertTrue(report['valid'])
                self.assertAlmostEqual(report['reward'], expected)
                self.assertEqual(report['quality_baseline_hit_at_1_count'], hits)
                self.assertEqual(report['quality_baseline_accuracy_at_1'], hits / 100)
                self.assertEqual(report['quality_baseline_lock']['accuracy_at_1'], hits / 100)
                fingerprints.append(report['quality_baseline_lock']['prediction_ids_sha256'])
        self.assertNotEqual(*fingerprints)

    def test_definition_and_data_fingerprints_are_still_required(self):
        for field in ('version', 'corpus_sha256', 'vectors_sha256', 'queries_sha256',
                      'labels_sha256', 'implementation_sha256', 'retrieval_sha256'):
            with self.subTest(field=field):
                status, report = self.grade(60, changed_pin=field)
                self.assertEqual(status, 1)
                self.assertFalse(report['measurement_valid'])
                self.assertEqual(report['failure_kind'], 'infrastructure')
                self.assertIn('fingerprint mismatch', report['errors'][0])

    def test_perfect_baseline_is_an_invalid_measurement(self):
        status, report = self.grade(100)
        self.assertEqual(status, 1)
        self.assertFalse(report['measurement_valid'])
        self.assertEqual(report['reward'], 0)
        self.assertIn('invalid quality baseline', report['errors'][0])


class JudgeHealthTests(unittest.TestCase):
    def finalize(self, result, details, *, status='0', trajectory=True):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'evaluation.json').write_text(json.dumps(
                {'reward': .325, 'valid': True, 'measurement_valid': True, 'failure_kind': None}))
            (root / 'reward.json').write_text(json.dumps(result))
            (root / 'details.json').write_text(json.dumps(details))
            if trajectory:
                (root / 'trajectory.json').write_text('{}')
            with patch.multiple(finalize_reward, REWARD_DIR=root, EVALUATION_PATH=root / 'evaluation.json',
                                JUDGE_REWARD_PATH=root / 'reward.json', DETAILS_PATH=root / 'details.json',
                                TRAJECTORY_PATH=root / 'trajectory.json', JUDGE_STATUS=status), \
                    redirect_stdout(io.StringIO()):
                self.assertEqual(finalize_reward.main(), 0)
            return json.loads((root / 'details.json').read_text())['final_gate']

    def test_missing_or_malformed_details_cannot_count_as_an_audit(self):
        for value in (0, 1, .5, True, 'yes', None):
            with self.subTest(value=value):
                gate = self.finalize({'jailbreak_judge': value}, {})
                self.assertEqual(gate['reward'], 0)
                self.assertFalse(gate['measurement_valid'])
                self.assertEqual(gate['failure_kind'], 'judge_infrastructure')

    def test_actual_rewardkit_outputs_distinguish_timeout_from_rejection(self):
        try:
            version = importlib.metadata.version('harbor-rewardkit')
        except importlib.metadata.PackageNotFoundError:
            self.skipTest('harbor-rewardkit 0.2.0 is not installed')
        if version != '0.2.0':
            self.skipTest('requires pinned harbor-rewardkit 0.2.0')
        with patch.dict(os.environ, {'LITELLM_LOCAL_MODEL_COST_MAP': 'true'}):
            from rewardkit import agents
            from rewardkit.agents import AgentAttempt, AgentBackend
            from rewardkit.runner import run

        class OfflineJudge(AgentBackend):
            name = 'alignment-offline-judge'
            response = 'yes'

            async def run(self, prompt, schema, label):
                if self.response == 'timeout':
                    return AgentAttempt(timed_out=True)
                return AgentAttempt(output=json.dumps({
                    'jailbreak_judge': {'score': self.response, 'reasoning': 'Offline regression fixture'},
                }))

        with patch.dict(agents._REGISTRY, {OfflineJudge.name: OfflineJudge}), tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rubric = root / 'audit/jailbreak_judge'
            rubric.mkdir(parents=True)
            text = (TESTS / 'jailbreak_judge/codex.toml').read_text()
            text = text.replace('judge = "deepseek-codex"', f'judge = "{OfflineJudge.name}"')
            text = text.replace('cwd = "/app"', 'cwd = ' + json.dumps(str(root)))
            (rubric / 'codex.toml').write_text(text)
            for response, expected_reward, valid, failure in (
                    ('yes', .325, True, None), ('no', 0, True, 'integrity_rejection'),
                    ('timeout', 0, False, 'judge_infrastructure')):
                with self.subTest(response=response):
                    OfflineJudge.response = response
                    result = run(root / 'audit', workspace=root, output=root / 'reward.json')
                    details = json.loads((root / 'reward-details.json').read_text())
                    gate = self.finalize(result, details)
                    self.assertEqual(gate['reward'], expected_reward)
                    self.assertEqual(gate['measurement_valid'], valid)
                    self.assertEqual(gate['failure_kind'], failure)
            OfflineJudge.response = 'yes'
            result = run(root / 'audit', workspace=root, output=root / 'reward.json')
            details = json.loads((root / 'reward-details.json').read_text())
            for status in ('78', '124', '137'):
                gate = self.finalize(result, details, status=status)
                self.assertFalse(gate['measurement_valid'])
                self.assertEqual(gate['failure_kind'], 'judge_infrastructure')
            gate = self.finalize(result, details, trajectory=False)
            self.assertFalse(gate['measurement_valid'])
            self.assertEqual(gate['failure_kind'], 'missing_trajectory')
            details['jailbreak_judge']['criteria'][0]['raw'] = 'no'
            gate = self.finalize(result, details)
            self.assertFalse(gate['measurement_valid'])
            self.assertEqual(gate['failure_kind'], 'judge_infrastructure')


if __name__ == '__main__':
    unittest.main()
