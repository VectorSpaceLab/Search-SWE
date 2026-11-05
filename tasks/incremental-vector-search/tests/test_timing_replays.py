"""Median timing must keep five samples and the matching retrieval outputs."""
import copy
import unittest

from metrics import aggregate_replays


class ReplayTests(unittest.TestCase):
    def fixture(self):
        limits = {'build_seconds': 10, 'insert_seconds': 2, 'full_scan_seconds': [[50]]}
        replays = []
        for i in range(5):
            histogram = [0] * 101
            histogram[80 + i] = 1
            replays.append({'build_seconds': 1, 'insert_seconds': [.1],
                            'cells': [{'stage': 0, 'k': 100, 'seconds': i + 1,
                                       'recall': (80 + i) / 100, 'recall_histogram': histogram}]})
        return limits, replays

    def aggregate(self, replays, limits):
        return aggregate_replays(replays, limits, stages=1, batch_size=1, ks=(100,))

    def test_uses_quality_from_median_time_replay_not_best_quality(self):
        limits, replays = self.fixture()
        value = self.aggregate(replays, limits)
        self.assertEqual(value['cells'][0]['median_replay'], 2)
        self.assertEqual(value['cells'][0]['seconds'], 3)
        self.assertEqual(value['missing_neighbors'], 18)
        self.assertAlmostEqual(value['score'], .82)

    def test_two_timed_out_replays_are_infinite_samples_not_dropped(self):
        limits, replays = self.fixture()
        replays[3] = replays[4] = {'failure_kind': 'timing_timeout'}
        value = self.aggregate(replays, limits)
        self.assertEqual(value['cells'][0]['seconds'], 3)
        replays[2] = {'failure_kind': 'timing_timeout'}
        self.assertEqual(self.aggregate(replays, limits)['score'], 0)

    def test_one_invalid_execution_remains_a_failure(self):
        limits, replays = self.fixture()
        replays[0]['failure_kind'] = 'invalid_submission'
        self.assertEqual(self.aggregate(replays, limits)['score'], 0)

    def test_exactly_five_samples_are_required(self):
        limits, replays = self.fixture()
        for count in (0, 3, 4):
            with self.assertRaises(ValueError):
                self.aggregate(replays[:count], limits)

    def test_each_preparation_gate_uses_its_median(self):
        limits, replays = self.fixture()
        for row in replays[:2]:
            row['build_seconds'] = 20
            row['insert_seconds'] = [3]
        self.assertGreater(self.aggregate(replays, limits)['score'], 0)
        replays[2]['insert_seconds'] = [3]
        self.assertEqual(self.aggregate(replays, limits)['score'], 0)

    def test_one_fast_cell_cannot_subsidize_another(self):
        limits, replays = self.fixture()
        limits['full_scan_seconds'].append([20])
        for row in replays:
            row['insert_seconds'].append(.1)
            extra = copy.deepcopy(row['cells'][0])
            extra.update(stage=1, seconds=2.1)
            row['cells'].append(extra)
        value = aggregate_replays(replays, limits, stages=2, batch_size=1, ks=(100,))
        self.assertEqual(value['score'], 0)
        self.assertIn('stage 1', value['failure'])

    def test_empty_or_nonfinite_timing_cannot_pass(self):
        limits, replays = self.fixture()
        for row in replays[:3]:
            row['cells'][0]['seconds'] = float('nan')
        self.assertEqual(self.aggregate(replays, limits)['score'], 0)


if __name__ == '__main__':
    unittest.main()
