"""Scoring and verifier credential checks without running submitted code."""
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

import grade
from score import load_catalog, lookup, parse_json, score_one


class ContractTests(unittest.TestCase):
    def test_submission_environment_has_only_public_api_credentials(self):
        credentials = {
            'OPENROUTER_API_KEY': 'public-test-key',
            'JINA_API_KEY': 'public-jina-test-key',
            'OPENROUTER_API_BASE_URL': 'https://openrouter.ai/api/v1',
            'OPENAI_API_KEY': 'private-test-key',
            'VERIFIER_OPENAI_API_KEY': 'private-test-key',
            'ANSWER_JUDGE_API_KEY': 'private-test-key',
        }
        with patch.dict(os.environ, credentials, clear=True):
            env = grade.submission_env()
        for key in ('OPENROUTER_API_KEY', 'JINA_API_KEY', 'OPENROUTER_API_BASE_URL'):
            self.assertEqual(env[key], credentials[key])
        for key in ('OPENAI_API_KEY', 'VERIFIER_OPENAI_API_KEY', 'ANSWER_JUDGE_API_KEY'):
            self.assertNotIn(key, env)

    def test_complete_plans_and_missing_tables_or_joins(self):
        root = Path(__file__).resolve().parents[1]
        corpus = root / 'data/catalog.json'
        if not corpus.exists():
            self.skipTest('Restore the catalog asset to run scorer checks.')
        catalog = lookup(load_catalog(corpus))
        for split in (root / 'data/validation', root / 'tests/data'):
            for line in (split / 'labels.jsonl').read_text().splitlines():
                gold = json.loads(line)
                for plan in gold['acceptable_plans']:
                    with self.subTest(split=split.name, query=gold['query_id']):
                        tables = list(plan['table_ids'])
                        tables += [t for t in catalog[0] if t not in tables][:5 - len(tables)]
                        pred = {'query_id': gold['query_id'], 'table_ids': tables, 'joins': plan['joins']}
                        self.assertEqual(score_one(pred, gold, catalog)['joint_success'], 1)
                        self.assertFalse(score_one({**pred, 'table_ids': tables[:4]}, gold, catalog)['valid'])
                        self.assertEqual(score_one({**pred, 'joins': []}, gold, catalog)['joint_success'], 0)

    def test_duplicate_json_keys_are_invalid(self):
        with self.assertRaises(ValueError):
            parse_json('{"query_id":"first","query_id":"second"}')


if __name__ == '__main__':
    unittest.main()
