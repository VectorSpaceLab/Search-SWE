import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import finalize


class FinalizationTests(unittest.TestCase):
    def test_discovery_import_does_not_read_or_write_results(self):
        spec = importlib.util.spec_from_file_location('discovery_probe', finalize.__file__)
        module = importlib.util.module_from_spec(spec)
        with patch('pathlib.Path.read_text', side_effect=AssertionError('import read results')), \
             patch('pathlib.Path.write_text', side_effect=AssertionError('import changed results')):
            spec.loader.exec_module(module)

    def test_reward_requires_successful_audit(self):
        for status, audit, expected in [('0', {'integrity': 1}, .7),
                                         ('1', {'integrity': 1}, 0),
                                         ('0', {'integrity': 0}, 0),
                                         ('0', None, 0)]:
            with self.subTest(status=status, audit=audit), tempfile.TemporaryDirectory() as d:
                root = Path(d)
                (root / 'evaluation.json').write_text(json.dumps({'deterministic_reward': .7}))
                if audit is not None:
                    (root / 'audit.json').write_text(json.dumps(audit))
                with patch.object(finalize, 'Path', return_value=root), \
                     patch.dict('os.environ', {'JUDGE_STATUS': status}):
                    if expected:
                        finalize.main()
                    else:
                        with self.assertRaises(SystemExit):
                            finalize.main()
                self.assertEqual(json.loads((root / 'reward.json').read_text())['reward'], expected)


if __name__ == '__main__':
    unittest.main()
