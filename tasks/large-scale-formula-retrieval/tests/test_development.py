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
        self.memory(0, 0)

    def memory(self, oom, oom_kill):
        (self.evidence / 'agent.json').write_text(json.dumps({
            'memory_events': f'oom {oom}\noom_kill {oom_kill}\n'}))

    def test_native_log_is_not_required(self):
        record, failure = check_development(self.evidence)
        self.assertIsNone(failure)
        self.assertEqual(record, json.loads((self.evidence / 'agent.json').read_text()))

    def test_agent_timeout_does_not_reject_collected_submission(self):
        # Harbor still collects the submission when codex exec has no completed
        # output. Neither this log nor its command counts are a scoring gate.
        (self.root / 'trial.log').write_text(
            'Running command: codex exec\n'
            'Running command: credential cleanup\nCommand outputs captured\n'
            'Collecting main service artifacts\n')
        self.assertIsNone(check_development(self.evidence)[1])

    def test_development_oom(self):
        for oom, oom_kill in [(1, 0), (0, 1), (2, 2)]:
            with self.subTest(oom=oom, oom_kill=oom_kill):
                self.memory(oom, oom_kill)
                self.assertEqual(check_development(self.evidence)[1], 'development memory limit')

    def test_missing_memory_evidence_is_an_error(self):
        (self.evidence / 'agent.json').unlink()
        with self.assertRaises(FileNotFoundError):
            check_development(self.evidence)

    def test_malformed_memory_evidence_is_an_error(self):
        for content in ['{', '{}', '{"memory_events": null}',
                        '{"memory_events": ""}', '{"memory_events": "oom 0"}',
                        '{"memory_events": "oom_kill 0"}',
                        '{"memory_events": "oom unknown\\noom_kill 0"}',
                        '{"memory_events": "oom -1\\noom_kill 0"}']:
            (self.evidence / 'agent.json').write_text(content)
            with self.subTest(content=content), self.assertRaises(
                    (ValueError, KeyError, AttributeError)):
                check_development(self.evidence)

    def test_evidence_privacy(self):
        self.evidence.chmod(0o755)
        with self.assertRaisesRegex(RuntimeError, 'private'):
            check_development(self.evidence)
