import json
from pathlib import Path
import tempfile
import unittest

from development import check_development


class DevelopmentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.evidence = self.root / 'evidence'
        self.evidence.mkdir(mode=0o700)
        self.log_dir = self.root / 'native'
        self.log_dir.mkdir(mode=0o700)
        self.log = self.log_dir / 'trial.log'
        self.memory(0)

    def memory(self, oom):
        (self.evidence / 'agent.json').write_text(json.dumps({
            'memory_events': f'oom {oom}\noom_kill {oom}\n'}))

    def check(self, content):
        self.log.write_text(content)
        return check_development(self.evidence, self.log)[1]

    def test_completed_agent(self):
        self.assertIsNone(self.check('Running command: codex exec\nCommand outputs captured\n'
                                     'Collecting main service artifacts\nRunning command: verifier\n'))

    def test_timeout_then_successful_cleanup(self):
        self.assertIn('incomplete', self.check('Running command: codex exec\n'
                      'Running command: credential cleanup\nCommand outputs captured\n'
                      'Collecting main service artifacts\n'))

    def test_development_oom(self):
        self.memory(1)
        self.assertEqual(self.check(''), 'development memory limit')

    def test_missing_boundary_is_infrastructure_error(self):
        with self.assertRaisesRegex(RuntimeError, 'boundary'):
            self.check('Running command: codex exec\nCommand outputs captured\n')

    def test_empty_or_unbalanced_evidence(self):
        for content in ['Collecting main service artifacts\n',
                        'Running command: codex exec\nCommand outputs captured\n'
                        'Command outputs captured\nCollecting main service artifacts\n']:
            with self.subTest(content=content), self.assertRaisesRegex(RuntimeError, 'Invalid native'):
                self.check(content)

    def test_evidence_privacy(self):
        self.log_dir.chmod(0o755)
        with self.assertRaisesRegex(RuntimeError, 'private'):
            self.check('')
