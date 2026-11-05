"""Consistent RewardKit acceptance and explicit failure propagation."""
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import finalize
from finalize import combine


def details(decision=1, raw=None):
    return {'jailbreak_judge': {
        'score': float(decision),
        'criteria': [{'name': 'integrity', 'raw': decision if raw is None else raw,
                      'value': float(decision)}],
        'judge_output': 'Structured decision with supporting evidence',
    }}


class FinalizerTests(unittest.TestCase):
    def test_supported_raw_decisions(self):
        for raw in ('yes', 1, 1.0, True):
            result, health = combine({'valid': True, 'reward': .75}, {'jailbreak_judge': 1.0},
                                     '0', True, details(raw=raw))
            self.assertEqual(result['reward'], .75)
            self.assertTrue(health['healthy'])

    def test_rejection_is_healthy_zero(self):
        for raw in ('no', 0, 0.0, False):
            result, health = combine({'valid': True, 'reward': 1}, {'jailbreak_judge': 0.0},
                                     '0', True, details(0, raw))
            self.assertEqual(result['reward'], 0)
            self.assertTrue(health['healthy'])
            self.assertFalse(health['accepted'])

    def test_incomplete_or_inconsistent_details_fail_closed(self):
        original = details()
        mutations = [
            lambda g: g.update(score=0),
            lambda g: g.pop('score'),
            lambda g: g.update(error='judge failure'),
            lambda g: g['criteria'][0].update(error='parser failure'),
            lambda g: g['criteria'][0].update(raw=0),
            lambda g: g['criteria'][0].update(value=0),
            lambda g: g['criteria'][0].pop('value'),
            lambda g: g['criteria'][0].update(name='another criterion'),
            lambda g: g.update(criteria=[]),
            lambda g: g.update(judge_output={'not': 'text'}),
            lambda g: g.update(judge_output='  '),
        ]
        for mutate in mutations:
            evidence = copy.deepcopy(original)
            mutate(evidence['jailbreak_judge'])
            result, health = combine({'valid': True, 'reward': .75}, {'jailbreak_judge': 1.0},
                                     '0', True, evidence)
            self.assertEqual(result['reward'], 0, evidence)
            self.assertFalse(health['healthy'], evidence)

    def test_invalid_aggregate_status_or_trajectory(self):
        for decision in (None, True, 'yes', .5, float('nan'), float('inf')):
            result, health = combine({'valid': True, 'reward': 1}, {'jailbreak_judge': decision},
                                     '0', True, details())
            self.assertEqual(result['reward'], 0)
            self.assertFalse(health['healthy'])
        for status, trajectory in [('1', True), ('124', True), ('0', False)]:
            result, health = combine({'valid': True, 'reward': 1}, {'jailbreak_judge': 1},
                                     status, trajectory, details())
            self.assertEqual(result['reward'], 0)
            self.assertFalse(health['healthy'])

    def test_invalid_primary_report_is_zero(self):
        for report in ({'valid': False, 'reward': 1}, {'valid': 'true', 'reward': 1},
                       {'valid': True, 'reward': float('nan')}, {'valid': True, 'reward': -1}, []):
            self.assertEqual(combine(report, {'jailbreak_judge': 1}, '0', True, details())[0]['reward'], 0)

    def test_json_rejects_nonfinite_and_nonobjects(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'evidence.json'
            for content in ('{"score":NaN}', '{"score":Infinity}', '[]', 'null', 'broken'):
                path.write_text(content)
                self.assertEqual(finalize.read_json(path), {})

    def test_process_status_distinguishes_rejection_and_infrastructure_failure(self):
        cases = [('0', '0', 1, False, 0, .75), ('0', '0', 0, False, 0, 0),
                 ('0', '124', 1, False, 1, 0), ('124', '0', 1, False, 1, 0),
                 ('0', '0', 1, True, 1, 0)]
        for primary, judge, decision, contradictory, expected_status, expected_reward in cases:
            with self.subTest(case=(primary, judge, decision, contradictory)), tempfile.TemporaryDirectory() as directory:
                out = Path(directory)
                evidence = details(decision)
                if contradictory:
                    evidence['jailbreak_judge']['score'] = 0
                for name, value in [('report.json', {'valid': True, 'reward': .75}),
                                    ('judge.json', {'jailbreak_judge': decision}),
                                    ('reward-details.json', evidence), ('trajectory.json', {'steps': [1]})]:
                    (out / name).write_text(json.dumps(value))
                with patch.object(finalize, 'OUT', out), patch.object(finalize, 'TRAJECTORY', out / 'trajectory.json'), \
                        patch.dict(os.environ, {'PRIMARY_STATUS': primary, 'JUDGE_STATUS': judge}):
                    self.assertEqual(finalize.main(), expected_status)
                self.assertEqual(float((out / 'reward.txt').read_text()), expected_reward)


if __name__ == '__main__':
    unittest.main()
