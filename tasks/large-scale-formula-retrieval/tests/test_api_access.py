"""Submission API credentials are available only to the build worker."""
import os
import unittest
from unittest.mock import patch

from runtime import submission_env


class ApiEnvironmentTests(unittest.TestCase):
    def test_build_receives_only_submission_api_credentials(self):
        supplied = {
            'OPENROUTER_API_KEY': 'test-submission-openrouter',
            'JINA_API_KEY': 'test-submission-jina',
            'OPENROUTER_API_BASE_URL': 'https://openrouter.ai/api/v1',
            'OPENAI_API_KEY': 'test-judge',
            'OPENAI_BASE_URL': 'https://judge.invalid',
            'AGENT_OPENROUTER_API_KEY': 'test-coding-agent',
            'VERIFIER_OPENAI_API_KEY': 'test-private-judge',
        }
        with patch.dict(os.environ, supplied, clear=True):
            build = submission_env('/work/runtime', [0, 1], allow_api=True)
            serving = submission_env('/serve/runtime', [0, 1])
        for name in ('OPENROUTER_API_KEY', 'JINA_API_KEY', 'OPENROUTER_API_BASE_URL'):
            self.assertEqual(build[name], supplied[name])
            self.assertNotIn(name, serving)
        for name in ('OPENAI_API_KEY', 'OPENAI_BASE_URL', 'AGENT_OPENROUTER_API_KEY', 'VERIFIER_OPENAI_API_KEY'):
            self.assertNotIn(name, build)
            self.assertNotIn(name, serving)
        self.assertEqual(build['HOME'], '/work/runtime')
        self.assertEqual(serving['HOME'], '/serve/runtime')
        self.assertEqual(build['OMP_NUM_THREADS'], '2')

    def test_api_is_optional_for_local_builds(self):
        with patch.dict(os.environ, {}, clear=True):
            env = submission_env('/work/runtime', [0, 1], allow_api=True)
        self.assertNotIn('OPENROUTER_API_KEY', env)
        self.assertNotIn('JINA_API_KEY', env)


if __name__ == '__main__':
    unittest.main()
