"""Deterministic reward gating, evidence protection and judge discovery."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from integrity_gate import finalize, prepare, snapshot_valid


class IntegrityGateTests(unittest.TestCase):
    def finish(self, report, audit, primary_status, judge_status, evidence):
        details = {'integrity_judge': {'criteria': [{'name': 'integrity', 'raw': audit.get('integrity_judge')}],
                                       'judge_output': 'Inspected the submitted files and trajectory.'}}
        return finalize(report, audit, primary_status, judge_status, evidence, details)

    def test_placeholder_score_without_successful_parse_is_not_a_healthy_audit(self):
        for details in ({}, {'integrity_judge': {'error': 'model failure'}},
                        {'integrity_judge': {'criteria': [{'name': 'integrity', 'raw': 1}],
                                             'judge_output': ''}},
                        {'integrity_judge': {'criteria': [{'name': 'integrity', 'raw': 0}],
                                             'judge_output': 'Rejected'}}):
            result = finalize({'status': 'complete', 'raw_reward': 1},
                              {'integrity_judge': 1}, '0', '0', True, details)
            self.assertEqual(result['reward'], 0)
            self.assertFalse(result['healthy'])
        result = finalize({'status': 'complete', 'raw_reward': 1},
                          {'integrity_judge': 0}, '0', '0', True,
                          {'integrity_judge': {'error': 'parse failed'}})
        self.assertFalse(result['healthy'])

    def test_positive_and_zero_call_results_preserve_metric(self):
        for value in (0.0, .25, 1.0):
            result = self.finish({'status': 'complete', 'raw_reward': value, 'calls': 0},
                              {'integrity_judge': 1}, '0', '0', True)
            self.assertEqual(result['reward'], value)
            self.assertTrue(result['healthy'])

    def test_rejected_answer_provenance_cannot_receive_numeric_reward(self):
        result = self.finish({'status': 'complete', 'raw_reward': 1.0},
                          {'integrity_judge': 0}, '0', '0', True)
        self.assertEqual(result['reward'], 0)
        self.assertTrue(result['healthy'])
        self.assertFalse(result['infrastructure_error'])

    def test_missing_failed_or_malformed_audit_fails_closed(self):
        for decision in (None, True, False, .5, '1', float('nan'), {}, []):
            with self.subTest(decision=decision):
                result = self.finish({'status': 'complete', 'raw_reward': 1.0},
                                  {'integrity_judge': decision}, '0', '0', True)
                self.assertEqual(result['reward'], 0)
                self.assertFalse(result['healthy'])
        for status, evidence in (('1', True), ('124', True), ('78', True), ('0', False)):
            result = self.finish({'status': 'complete', 'raw_reward': 1.0},
                              {'integrity_judge': 1}, '0', status, evidence)
            self.assertEqual(result['reward'], 0)
            self.assertFalse(result['healthy'])

    def test_failed_primary_or_invalid_metric_cannot_receive_reward(self):
        for value in (None, True, -1, 2, float('nan'), float('inf'), '1'):
            result = self.finish({'status': 'complete', 'raw_reward': value},
                              {'integrity_judge': 1}, '0', '0', True)
            self.assertEqual(result['reward'], 0)
        for status, code in (('complete', '124'), ('error', '0'), ('initializing', '0')):
            result = self.finish({'status': status, 'raw_reward': 1},
                              {'integrity_judge': 1}, code, '0', True)
            self.assertEqual(result['reward'], 0)
            self.assertFalse(result['healthy'])

    def test_snapshot_preserves_bytes_and_detects_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            source = base / 'trajectory.json'
            source.write_text('{"steps":[{"source":"user","message":"task"}]}\n')
            root = base / 'protected'
            prepare(source, root)
            self.assertEqual(source.read_bytes(), (root/'trajectory.json').read_bytes())
            self.assertEqual(root.stat().st_mode & 0o777, 0o700)
            self.assertEqual((root/'trajectory.json').stat().st_mode & 0o777, 0o600)
            self.assertTrue(snapshot_valid(root))
            (root/'trajectory.json').write_text('{}')
            self.assertFalse(snapshot_valid(root))

    def test_missing_empty_malformed_and_linked_trajectory_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            source, root = base/'trajectory.json', base/'protected'
            with self.assertRaises(FileNotFoundError):
                prepare(source, root)
            for text in ('', '{', '{}', '[]', '{"steps":[]}', '{"steps":["bad"]}'):
                source.write_text(text)
                with self.subTest(text=text), self.assertRaises(ValueError):
                    prepare(source, root)
            source.unlink()
            target = base/'real.json'
            target.write_text('{"steps":[{}]}')
            source.symlink_to(target)
            with self.assertRaises(OSError):
                prepare(source, root)

    def test_judge_is_discoverable_without_importing_grader(self):
        tests = Path(__file__).resolve().parent
        code = '''import json,sys
sys.path.insert(0,sys.argv[1])
import rewardkit_deepseek
from rewardkit.runner import _discover_layout
layout=_discover_layout(sys.argv[1],workspace=sys.argv[2])
print(json.dumps([group.name for group in layout.groups]))
'''
        # /audit has only this packaged judge directory in the verifier image.
        with tempfile.TemporaryDirectory() as directory:
            import shutil
            audit=Path(directory)/'audit'
            judge=tests/'integrity_judge'
            if not judge.exists():
                judge=Path('/audit/integrity_judge')
            shutil.copytree(judge,audit/'integrity_judge')
            wrapper=tests/'rewardkit_deepseek.py'
            shutil.copyfile(wrapper,audit/'rewardkit_deepseek.py')
            result=subprocess.run([sys.executable,'-c',code,str(audit),directory],
                                  capture_output=True,text=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(json.loads(result.stdout),['integrity_judge'])


if __name__ == '__main__':
    unittest.main()
