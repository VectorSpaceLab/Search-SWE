"""Offline judge transport checks; these do not test model semantic accuracy."""
import json
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

import grader as g


class JudgeRequestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = json.loads((Path(__file__).with_name('judge_calibration.json')).read_text())

    def setUp(self):
        self.config = g.JudgeConfig('https://openrouter.ai/api/v1', 'offline-placeholder')

    def test_request_preserves_question_evidence_and_requirements(self):
        # All verdicts below are mocked: this checks transport, not the case labels.
        for case in self.cases:
            with self.subTest(case=case['case_id']):
                response = Mock(status_code=200)
                response.json.return_value = {'id': 'offline', 'model': g.MODEL,
                    'choices': [{'message': {'content': json.dumps({
                        'supported': case['expected_supported'], 'reason': 'mocked verdict'})}}]}
                with patch.object(g.requests, 'post', return_value=response) as post:
                    result = g.call_judge(self.config, case['question'],
                                          case['candidate_sentences'], case['reference'])
                args, kwargs = post.call_args
                self.assertEqual(args, (self.config.api_base + '/chat/completions',))
                self.assertEqual(kwargs['timeout'], (10, 120))
                body = kwargs['json']
                self.assertEqual(body['messages'][0], {'role': 'system', 'content': g.SYSTEM_PROMPT})
                self.assertEqual(json.loads(body['messages'][1]['content']), {
                    'QUESTION': case['question'],
                    'CANDIDATE_SENTENCES': case['candidate_sentences'],
                    'REFERENCE': case['reference']})
                # The expected answer and author rationale are never sent to the judge.
                self.assertEqual(body['model'], g.MODEL)
                self.assertEqual(body['reasoning'], {'effort': g.EFFORT, 'exclude': True})
                self.assertEqual(body['temperature'], 0)
                self.assertIs(result['supported'], case['expected_supported'])
                self.assertEqual(result['attempts'], 1)
                post.assert_called_once()

    def test_malformed_judgments_fail_closed_after_bounded_retry(self):
        response = Mock(status_code=200)
        response.json.return_value = {'choices': [{'message': {
            'content': '{"supported":"true","reason":"not a boolean"}'}}]}
        with patch.object(g.requests, 'post', return_value=response) as post, \
                patch.object(g.time, 'sleep'):
            with self.assertRaisesRegex(g.VerificationError, 'invalid judge decision schema'):
                g.call_judge(self.config, 'Question?', ['Evidence.'],
                             {'requirements': ['Requirement.'], 'sentences': ['Reference.']})
        self.assertEqual(post.call_count, 2)


if __name__ == '__main__':
    unittest.main()
