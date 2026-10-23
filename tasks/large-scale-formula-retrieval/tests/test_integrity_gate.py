"""Integrity reward gates, protected evidence and installed judge discovery."""
import ast
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import tomllib
import unittest

import integrity_gate as gate


def details(decision):
    return {'integrity_judge': {'criteria': [{'name': 'integrity',
            'raw': 'yes' if decision else 'no', 'value': decision}],
            'judge_output': 'Reviewed the submission and trajectory.'}}


class IntegrityGateTests(unittest.TestCase):
    def report(self, value):
        return {gate.METRIC_FIELD: value, gate.VALID_FIELD: True}

    def test_accepting_audit_preserves_the_numeric_score(self):
        for value in (0.0, .25, 1.0):
            result = gate.finalize(self.report(value), {'integrity_judge': 1},
                                   '0', '0', True, details(1))
            self.assertEqual(result['reward'], value)
            self.assertTrue(result['healthy'])

    def test_rejected_answer_provenance_cannot_receive_reward(self):
        result = gate.finalize(self.report(1.0), {'integrity_judge': 0},
                               '0', '0', True, details(0))
        self.assertEqual(result['reward'], 0)
        self.assertTrue(result['healthy'])
        self.assertFalse(result['infrastructure_error'])

    def test_missing_failed_or_malformed_audit_fails_closed(self):
        for value in (None, True, False, .5, '1', float('nan'), {}, []):
            with self.subTest(decision=value):
                result = gate.finalize(self.report(1), {'integrity_judge': value},
                                       '0', '0', True, details(1))
                self.assertEqual(result['reward'], 0)
                self.assertFalse(result['healthy'])
        for status, evidence in (('1', True), ('124', True), ('78', True), ('0', False)):
            result = gate.finalize(self.report(1), {'integrity_judge': 1},
                                   '0', status, evidence, details(1))
            self.assertEqual(result['reward'], 0)
            self.assertFalse(result['healthy'])

    def test_audit_requires_parsed_consistent_evidence(self):
        cases = [{}, {'integrity_judge': []}, {'integrity_judge': {'criteria': []}}, details(0)]
        for field, value in [('judge_output', ''), ('error', 'parse failed')]:
            malformed = details(1)
            malformed['integrity_judge'][field] = value
            cases.append(malformed)
        malformed = details(1)
        malformed['integrity_judge']['criteria'][0]['raw'] = 'perhaps'
        cases.append(malformed)
        for detail in cases:
            result = gate.finalize(self.report(1), {'integrity_judge': 1},
                                   '0', '0', True, detail)
            self.assertEqual(result['reward'], 0)
            self.assertFalse(result['healthy'])

    def test_failed_primary_and_invalid_metrics_fail_closed(self):
        for value in (None, True, -1, 2, float('nan'), float('inf'), '1'):
            result = gate.finalize(self.report(value), {'integrity_judge': 1},
                                   '0', '0', True, details(1))
            self.assertEqual(result['reward'], 0)
        for report, status in ((self.report(1), '124'), ({gate.METRIC_FIELD: 1}, '0')):
            result = gate.finalize(report, {'integrity_judge': 1}, status, '0', True, details(1))
            self.assertEqual(result['reward'], 0)
            self.assertFalse(result['healthy'])

    def test_protected_snapshot_preserves_bytes_and_detects_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            source = base / 'trajectory.json'
            source.write_text('{"steps":[{"source":"user","message":"task"}]}')
            root = base / 'protected'
            gate.prepare(source, root)
            self.assertEqual(source.read_bytes(), (root/'trajectory.json').read_bytes())
            self.assertEqual(root.stat().st_mode & 0o777, 0o700)
            self.assertEqual((root/'trajectory.json').stat().st_mode & 0o777, 0o600)
            self.assertTrue(gate.snapshot_valid(root))
            (root/'trajectory.json').write_text('{}')
            self.assertFalse(gate.snapshot_valid(root))

    def test_missing_empty_malformed_and_linked_trajectory_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            source, root = base/'trajectory.json', base/'protected'
            with self.assertRaises(FileNotFoundError):
                gate.prepare(source, root)
            for text in ('', '{', '{}', '[]', '{"steps":[]}', '{"steps":["bad"]}'):
                source.write_text(text)
                with self.subTest(text=text), self.assertRaises(ValueError):
                    gate.prepare(source, root)
            source.unlink()
            target = base/'real.json'
            target.write_text('{"steps":[{}]}')
            source.symlink_to(target)
            with self.assertRaises(OSError):
                gate.prepare(source, root)

    def test_judge_discovery_in_verifier_only_layout(self):
        tests = Path(__file__).resolve().parent
        code = """import json,sys
sys.path.insert(0,sys.argv[1])
import rewardkit_deepseek
from rewardkit.runner import _discover_layout
layout=_discover_layout(sys.argv[1],workspace=sys.argv[2])
print(json.dumps([group.name for group in layout.groups]))
"""
        with tempfile.TemporaryDirectory() as directory:
            audit = Path(directory)/'audit'
            shutil.copytree(tests/'integrity_judge', audit/'integrity_judge')
            shutil.copyfile(tests/'rewardkit_deepseek.py', audit/'rewardkit_deepseek.py')
            result = subprocess.run([sys.executable, '-c', code, str(audit), directory],
                                    capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout), ['integrity_judge'])

    def test_verifier_metadata_and_entrypoint(self):
        tests = Path(__file__).resolve().parent
        if not (tests.parent/'task.toml').exists():
            self.skipTest('Repository metadata is not installed in verifier images')
        config = tomllib.loads((tests.parent/'task.toml').read_text())
        self.assertIn('/logs/agent/trajectory.json', config['artifacts'])
        self.assertEqual(config['verifier']['allowed_hosts'], ['openrouter.ai'])
        self.assertEqual(config['verifier']['network_mode'], 'allowlist')
        self.assertNotIn('OPENAI_API_KEY', config['agent'].get('env', {}))
        for variable in ('OPENAI_API_KEY', 'OPENAI_BASE_URL'):
            self.assertIn('VERIFIER_', config['verifier']['env'][variable])
        entry = (tests/'test.sh').read_text()
        self.assertLess(entry.index('integrity_gate.py prepare'), entry.index('primary_status=0'))
        self.assertLess(entry.index('integrity_gate.py cleanup'), entry.index('rewardkit_deepseek.py'))
        self.assertLess(entry.index('rewardkit_deepseek.py'), entry.index('integrity_gate.py finalize'))
        judge = tomllib.loads((tests/'integrity_judge/codex.toml').read_text())
        self.assertEqual(judge['judge']['atif-trajectory'], '/logs/verifier/trajectory.json')
        self.assertEqual(judge['criterion'][0]['name'], 'integrity')
        self.assertEqual(judge['judge']['model'], 'deepseek/deepseek-v4.1-flash')

    def test_numeric_grader_does_not_publish_a_final_reward(self):
        tests = Path(__file__).resolve().parent
        grader = tests/'grader.py'
        if grader.exists():
            source = grader.read_text()
            self.assertNotIn("write('reward.json'", source)
            self.assertNotIn("(LOG / 'reward.txt').write_text", source)
            self.assertIn("'raw_reward'", source)
            # Every dictionary update must use the intermediate metric field too.
            for node in ast.walk(ast.parse(source)):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == 'update':
                    self.assertNotIn('reward', {keyword.arg for keyword in node.keywords})

    def test_multivector_entrypoint_fingerprint(self):
        tests = Path(__file__).resolve().parent
        limits = tests/'runtime_limits.py'
        if not limits.exists():
            return
        tree = ast.parse(limits.read_text())
        ref = ast.literal_eval(tree.body[1].value)
        if 'verifier_entrypoint_sha256' in ref:
            self.assertEqual(ref['verifier_entrypoint_sha256'], hashlib.sha256((tests/'test.sh').read_bytes()).hexdigest())


if __name__ == '__main__':
    unittest.main()
