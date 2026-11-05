"""Offline judge transport checks; these do not test model semantic accuracy."""
import json
import math
from pathlib import Path
import re
import tomllib
import unittest
from unittest.mock import Mock, patch

import grader as g


class JudgeRequestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = json.loads((Path(__file__).with_name('judge_calibration.json')).read_text())

    def setUp(self):
        self.settings = {'ANSWER_JUDGE_BASE_URL':'https://judge.example.test/v1/',
                         'ANSWER_JUDGE_API_KEY':'offline-placeholder',
                         'ANSWER_JUDGE_MODEL_NAME':'configured-judge-model'}
        with patch.dict(g.os.environ,self.settings,clear=True):
            self.config = g.judge_config()

    def test_all_judge_settings_are_required_without_model_or_key_fallbacks(self):
        self.assertEqual(self.config,g.JudgeConfig('https://judge.example.test/v1',
                                                'offline-placeholder','configured-judge-model'))
        for name in self.settings:
            for value in [None,'','  ']:
                env=dict(self.settings,OPENROUTER_API_KEY='not-a-judge-credential')
                if value is None:
                    del env[name]
                else:
                    env[name]=value
                with self.subTest(name=name,value=value),patch.dict(g.os.environ,env,clear=True):
                    with self.assertRaisesRegex(g.VerificationError,name):
                        g.judge_config()

    def test_task_passes_judge_settings_only_to_the_verifier(self):
        task=Path(__file__).resolve().parents[1]
        config=tomllib.loads((task/'task.toml').read_text())
        for name in self.settings:
            self.assertEqual(config['verifier']['env'][name],'${'+name+':-}')
            self.assertNotIn(name,config['environment']['env'])

    def test_nested_timeouts_cover_three_rounds_and_bounded_retries(self):
        task=Path(__file__).resolve().parents[1]
        config=tomllib.loads((task/'task.toml').read_text())
        shell=(task/'tests/test.sh').read_text()
        phases=[int(s) for s in re.findall(r'--kill-after=30s (\d+)s',shell)]
        self.assertEqual(len(phases),2)
        judge_budget,audit_budget=phases
        hidden_count=sum(bool(line.strip()) for line in (task/'tests/data/queries.jsonl').read_text().splitlines())
        attempts,connect_timeout,read_timeout,retry_delay=2,10,120,2
        round_budget=attempts*(connect_timeout+read_timeout)+retry_delay
        judge_waves=math.ceil(hidden_count*g.JUDGE_REPEATS/g.JUDGE_WORKERS)
        self.assertGreater(judge_budget,judge_waves*round_budget)
        build_budget=int(re.search(r'^BUILD_TIMEOUT_SECONDS=(\d+)$',shell,re.M)[1])
        run_budget=int(re.search(r'^RUN_TIMEOUT_SECONDS=(\d+)$',shell,re.M)[1])
        # Two timeout kill graces plus room for staging, cleanup and finalization.
        required=build_budget+run_budget+judge_budget+audit_budget+2*30+120
        self.assertGreaterEqual(config['verifier']['timeout_sec'],required)

    def test_request_preserves_question_evidence_and_requirements(self):
        # All verdicts below are mocked: this checks transport, not the case labels.
        for case in self.cases:
            with self.subTest(case=case['case_id']):
                response = Mock(status_code=200)
                response.json.return_value = {'id': 'offline', 'model': self.config.model,
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
                self.assertEqual(body['model'], self.config.model)
                self.assertEqual(body['reasoning'], {'effort': g.EFFORT, 'exclude': True})
                self.assertEqual(body['temperature'], 0)
                self.assertEqual(body['max_tokens'], 8192)
                self.assertEqual(body['response_format'], {'type': 'json_object'})
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
