import json
from pathlib import Path
import tempfile
import unittest
from development import check_development


class DevelopmentEvidenceTests(unittest.TestCase):
    def test_trusted_timeout_and_oom_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            evidence = root / 'evidence'
            evidence.mkdir(mode=0o700)
            with self.assertRaises(FileNotFoundError):
                check_development(evidence)
            record = {'development_elapsed_seconds': 10, 'memory_events': 'oom 0\noom_kill 0\n', 'cgroup_memory_peak_bytes': 100}
            (evidence / 'agent.json').write_text(json.dumps(record))
            self.assertIsNone(check_development(evidence)[1])
            record['development_elapsed_seconds'] = 7200.001
            (evidence / 'agent.json').write_text(json.dumps(record))
            self.assertEqual(check_development(evidence)[1], 'development timeout')
            record['development_elapsed_seconds'] = 7200
            record['memory_events'] = 'oom 1\noom_kill 1\n'
            (evidence / 'agent.json').write_text(json.dumps(record))
            self.assertEqual(check_development(evidence)[1], 'development memory limit')
            evidence.chmod(0o755)
            with self.assertRaises(RuntimeError):
                check_development(evidence)


if __name__ == '__main__':
    unittest.main()
