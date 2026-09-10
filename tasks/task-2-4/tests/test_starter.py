import importlib.util
import json
from pathlib import Path
import unittest

SOURCE = Path(__file__).parents[1] / 'environment/starter/src/run_search.py'
SPEC = importlib.util.spec_from_file_location('react_starter', SOURCE)
STARTER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(STARTER)


class ReactTests(unittest.TestCase):
    def docs(self, query):
        return [{'docid': str(i), 'text': 'clue: ' + query} for i in range(7)]

    def test_repeated_search_planner_stops_at_twenty(self):
        planned = []
        def plan(messages):
            planned.append(messages[-1]['content'])
            return {'action': 'search', 'query': 'follow-up'}
        ids, trace = STARTER.retrieve('original', self.docs, plan)
        self.assertEqual(len(trace), 20)
        self.assertEqual(len(planned), 19)
        self.assertEqual(len(set(ids)), 5)
        self.assertEqual([s['round'] for s in trace], list(range(1, 21)))

    def test_observations_inform_next_search_and_early_finish(self):
        def plan(messages):
            observation = messages[-1]['content']
            if '"round": 1' in observation:
                self.assertIn('clue: original', observation)
                return {'action': 'search', 'query': 'new entity'}
            return {'action': 'finish', 'doc_ids': ['6', '5', '4', '3', '2']}
        ids, trace = STARTER.retrieve('original', self.docs, plan)
        self.assertEqual(ids, ['6', '5', '4', '3', '2'])
        self.assertEqual([s['query'] for s in trace], ['original', 'new entity'])

    def test_offline_baseline_and_invalid_finish_never_invent_ids(self):
        ids, trace = STARTER.retrieve('question', self.docs)
        self.assertEqual(len(trace), 1)
        ids, _ = STARTER.retrieve('question', self.docs,
                                  lambda _: {'action': 'finish', 'doc_ids': ['unknown', '0', '0']})
        self.assertEqual(len(set(ids)), 5)
        self.assertNotIn('unknown', ids)

    def test_cannot_raise_starter_round_limit(self):
        with self.assertRaises(ValueError):
            STARTER.retrieve('question', self.docs, max_rounds=21)


if __name__ == '__main__':
    unittest.main()
