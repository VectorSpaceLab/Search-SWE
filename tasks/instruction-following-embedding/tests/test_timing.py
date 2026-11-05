"""CPU-only regressions for query timing, invalid output and storage accounting."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'environment/runtime'))
import evaluate
from metrics import rank_vectors


class TimingTests(unittest.TestCase):
    def measure(self, durations, outputs=None, scoring_seconds=0):
        clock = [0.0]
        docs = np.eye(1024, dtype=np.float32)[:3]
        group = {'key': 'r/1', 'subset': 'r', 'query': 'q',
                 'instruction_og': 'include evidence', 'candidates': ['0', '1', '2']}
        index = {'r/' + str(i): i for i in range(3)}
        default = docs[0]
        pending = iter(zip(durations, outputs if outputs is not None else [default] * len(durations)))

        def call(message, deadline):
            self.assertEqual(message, {'query': 'q', 'instruction': 'include evidence'})
            self.assertAlmostEqual(deadline - clock[0], 1)
            duration, output = next(pending)
            clock[0] += duration
            if isinstance(output, Exception):
                raise output
            return output

        def score(vector, documents, candidates):
            clock[0] += scoring_seconds
            return rank_vectors(vector, documents, candidates)

        call = Mock(side_effect=call)
        recover = Mock()
        with patch.object(evaluate.time, 'monotonic', side_effect=lambda: clock[0]), \
                patch.object(evaluate, 'rank_vectors', side_effect=score):
            result = evaluate.measure_query(group, 'og', docs, index, call, recover)
        return result, call, recover

    def test_uses_median_sample_and_its_ranking_not_fastest(self):
        vectors = np.eye(1024, dtype=np.float32)[:3]
        (ranking, timing, errors), call, recover = self.measure(
            [.8, .2, .5, .1, .9], [vectors[0], vectors[0], vectors[2], vectors[1], vectors[0]])
        self.assertEqual(ranking[0], '2')
        self.assertAlmostEqual(timing['seconds'], .5)
        self.assertEqual(timing['selected_repeat'], 3)
        self.assertEqual(len(timing['samples']), 5)
        self.assertEqual(call.call_count, 5)
        self.assertEqual(errors, [])
        recover.assert_not_called()

    def test_timeouts_are_kept_in_population(self):
        vector = np.eye(1024, dtype=np.float32)[0]
        (ranking, timing, errors), call, recover = self.measure(
            [1, .1, 1, .2, .3], [TimeoutError('timeout'), vector, TimeoutError('timeout'), vector, vector])
        self.assertIsNotNone(ranking)
        self.assertAlmostEqual(timing['seconds'], .3)
        self.assertEqual(len(errors), 2)
        self.assertEqual(call.call_count, 5)
        self.assertEqual(recover.call_count, 2)

    def test_three_timeouts_fail_instead_of_resampling_successes(self):
        vector = np.eye(1024, dtype=np.float32)[0]
        (ranking, timing, _), call, recover = self.measure(
            [1, .1, 1, .2, 1], [TimeoutError(), vector, TimeoutError(), vector, TimeoutError()])
        self.assertIsNone(ranking)
        self.assertIsNone(timing['seconds'])
        self.assertEqual(call.call_count, 5)
        self.assertEqual(recover.call_count, 3)

    def test_complete_ranking_time_is_included(self):
        (ranking, timing, _), _, recover = self.measure([.81] * 5, scoring_seconds=.25)
        self.assertIsNone(ranking)
        self.assertTrue(all(s['status'] == 'timeout' for s in timing['samples']))
        self.assertTrue(all(s['seconds'] > 1 for s in timing['samples']))
        recover.assert_not_called()  # Worker already returned a complete response.

    def test_invalid_vector_cannot_be_voted_away(self):
        vector = np.eye(1024, dtype=np.float32)[0]
        (ranking, timing, errors), call, _ = self.measure(
            [.1] * 5, [vector, np.full(1024, np.nan), vector, vector, vector])
        self.assertIsNone(ranking)
        self.assertEqual(timing['samples'][-1]['status'], 'invalid')
        self.assertEqual(len(errors), 1)
        self.assertEqual(call.call_count, 2)

    def test_model_or_resource_violation_remains_global_failure(self):
        with self.assertRaises(evaluate.ResourceViolation):
            self.measure([.1], [evaluate.ResourceViolation('model execution constraint')])


class ResourceTests(unittest.TestCase):
    def test_single_gpu_and_disk_budget_without_capacity_requirement(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ['task/models', 'task/corpus', 'app', 'tmp']:
                (root / name).mkdir(parents=True)
            (root / 'task/models/config').write_bytes(b'x')
            with patch.object(evaluate, 'Path', side_effect=lambda p: root / p.lstrip('/')), \
                    patch.object(evaluate.pynvml, 'nvmlInit'), \
                    patch.object(evaluate.pynvml, 'nvmlDeviceGetCount', return_value=1), \
                    patch.object(evaluate.pynvml, 'nvmlDeviceGetMemoryInfo') as memory:
                resources = evaluate.Resources()
                resources.check()
                self.assertEqual(resources.report(), {'peak_task_storage_bytes': 1})
                memory.assert_not_called()
                with (root / 'tmp/sparse').open('wb') as file:
                    file.truncate(32 << 30)
                resources.last_disk = 0
                with self.assertRaises(evaluate.ResourceViolation):
                    resources.check()

    def test_multiple_gpus_still_rejected(self):
        with patch.object(evaluate.pynvml, 'nvmlInit'), \
                patch.object(evaluate.pynvml, 'nvmlDeviceGetCount', return_value=2):
            with self.assertRaisesRegex(RuntimeError, 'Exactly one'):
                evaluate.Resources()


if __name__ == '__main__':
    unittest.main()
