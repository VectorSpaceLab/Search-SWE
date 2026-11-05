"""Real subprocess isolation and platform preparation, in a disposable container only."""
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

import numpy as np

import calibrate_platform
import grader
from metrics import aggregate_replays
from runtime_limits import load_runtime_limits, platform_fingerprint


@unittest.skipUnless(os.environ.get('TASK_ISOLATION_TEST') == '1' and Path('/.dockerenv').exists(),
                     'Requires an explicitly disposable task container')
class ReplayIntegrationTests(unittest.TestCase):
    def test_single_preparation_and_five_fresh_submission_replays(self):
        source = Path(__file__).resolve().parents[1] / 'environment/exact_search.py'
        reference = Path('/task/reference')
        reference.mkdir(parents=True, exist_ok=True)
        Path('/task/assets.json').write_text('{"schema_version": 1, "files": []}')
        public_limits = Path('/task/platform/limits.json')
        public_limits.parent.mkdir(parents=True, exist_ok=True)
        public_limits.write_text('{"test_fixture": true}')
        # An inherited state file would fail the next replay before any build.
        code = source.read_text().replace('import json',
            "from pathlib import Path\nmarker = Path('/work/state/built')\n"
            "assert not marker.exists(), 'State leaked across replays'\nmarker.touch()\n"
            "limits = Path('/task/platform/limits.json')\nassert limits.read_text()\n"
            "try:\n    limits.write_text('tampered')\n"
            "except PermissionError:\n    pass\n"
            "else:\n    raise AssertionError('Public limits must be read-only')\nimport json", 1)
        # Tiny vector arithmetic is dominated by protocol/scheduler overhead.
        # Give this synthetic exact reference a deterministic extra cost so the
        # partial baseline has real headroom under its reference timing ceiling.
        (reference / 'exact_search.py').write_text(code.replace('print(json.dumps(response',
            "if op == 'search':\n        __import__('time').sleep(.003)\n    print(json.dumps(response"))
        # Use partial results to give the small synthetic baseline a known gap.
        partial = code.replace('print(json.dumps(response',
            "if op == 'search':\n        response = {key: value[:request['k'] // 2] for key, value in response.items()}\n    print(json.dumps(response")
        (reference / 'baseline_search.py').write_text(partial)
        rng = np.random.default_rng(340)
        corpus, private, validation = (Path(p) / '16' for p in
            ('/task/data/corpus', '/tests/data', '/task/data/validation'))
        for root in (corpus, private, validation):
            root.mkdir(parents=True, exist_ok=True)
        for root, name, count in ((corpus, 'initial', 1100), (corpus, 'warmup', 2),
                                  (private, 'inserts', 4), (private, 'queries', 4),
                                  (validation, 'initial', 1100), (validation, 'inserts', 1000),
                                  (validation, 'queries', 1000)):
            np.save(root / f'{name}.npy', rng.normal(size=(count, 16)).astype('float32'))
        before = platform_fingerprint()
        output = Path('/platform-test')
        with patch.object(grader, 'evaluate_dataset', wraps=grader.evaluate_dataset) as evaluate:
            config = calibrate_platform.calibrate(output, dimensions=(16,), initial_count=1100,
                                                 batch_size=2, stages=2)
        self.assertEqual(evaluate.call_count, 2)  # One exact run and one baseline run.
        self.assertTrue(all(call.kwargs['repeat'] == 0 for call in evaluate.call_args_list))
        self.assertEqual(config['reference_repeats'], 1)
        self.assertEqual(config['timing_repeats'], 5)
        self.assertEqual(platform_fingerprint(), before)
        self.assertEqual(load_runtime_limits(output / 'public/limits.json'), config)
        self.assertEqual(config['datasets']['16']['baseline_missing_neighbors'], 5000)
        self.assertTrue((output / 'validation/16/ground_truth.npy').is_file())
        exact = json.loads((output / 'diagnostics/16.exact.json').read_text())
        self.assertEqual(exact['missing_neighbors'], 0)
        self.assertEqual(len(exact['cells']), 10)
        # Reuse the prepared targets, then check a real deadline violation keeps
        # five infinite samples instead of silently shrinking the denominator.
        calibrate_platform.write_reference('exact_search.py')
        limits = dict(config['datasets']['16'], build_seconds=10, insert_seconds=2,
                      full_scan_seconds=[[1e-8] * 5 for _ in range(2)])
        replays = [grader.evaluate_dataset(16, limits, initial_count=1100,
                    batch_size=2, stages=2, repeat=i) for i in range(5)]
        self.assertTrue(all(r['failure_kind'] == 'timing_timeout' for r in replays))
        result = aggregate_replays(replays, limits, stages=2, batch_size=2)
        self.assertEqual(result['score'], 0)
        self.assertIn('Median query time', result['failure'])


if __name__ == '__main__':
    unittest.main()
