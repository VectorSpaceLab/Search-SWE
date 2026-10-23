import math
import unittest
from scoring import recall, dataset_score, validate_reference


class ScoringTests(unittest.TestCase):
    def setUp(self):
        self.ref = {'status': 'frozen', 'stages': 100, 'initial_rss_bytes': 2 << 30,
                    'live_rss_bytes': [1 << 30] * 100, 'memory_noise_bytes': 1000,
                    'full_scan_seconds': [1.0] * 100,
                    'build_timeout_seconds': 100, 'delete_timeout_seconds': 10,
                    'calibration_timeout_seconds': 30,
                    'config': {'test_query_count': 1},
                    'recall_baseline': {'status': 'frozen', 'recall': .901}}
        self.stages = [{'rss_bytes': 1.25 * (1 << 30), 'recall': .991, 'query_seconds': .1}] * 100

    def test_half_log_error_reduction(self):
        validate_reference(self.ref)
        score = dataset_score(self.stages, 2 << 30, self.ref)
        self.assertAlmostEqual(score['recall_gain'], .5)
        self.assertAlmostEqual(score['reward'], .475)

    def test_baseline_floor_and_perfect_recall(self):
        for r, gain in [(0, 0), (.89, 0), (.901, 0), (1, 1)]:
            with self.subTest(r=r):
                score = dataset_score([{'rss_bytes': 1 << 30, 'recall': r,
                                        'query_seconds': .1}] * 100, 2 << 30, self.ref)
                self.assertAlmostEqual(score['recall_gain'], gain)
                self.assertAlmostEqual(score['reward'], gain)

    def test_memory_credit_requires_retrieval_improvement(self):
        for r in [0, .89, .901]:
            for rss in [1 << 29, 1 << 30, 2 << 30]:
                with self.subTest(recall=r, rss=rss):
                    score = dataset_score([{'rss_bytes': rss, 'recall': r,
                                            'query_seconds': .1}] * 100, 2 << 30, self.ref)
                    self.assertEqual(score['reward'], 0)

    def test_quality_and_memory_endpoints(self):
        for r, gain in [(.991, .5), (1, 1)]:
            scores = []
            for rss, e in [(2 << 30, 0), (1.5 * (1 << 30), .5), (1 << 30, 1)]:
                with self.subTest(recall=r, memory_efficiency=e):
                    score = dataset_score([{'rss_bytes': rss, 'recall': r,
                                            'query_seconds': .1}] * 100, 2 << 30, self.ref)
                    self.assertAlmostEqual(score['reward'], gain * (.8 + .2 * e))
                    scores.append(score['reward'])
            self.assertLess(scores[0], scores[1])
            self.assertLess(scores[1], scores[2])

    def test_missing_or_degenerate_baseline_is_setup_error(self):
        for baseline in [{}, {'status': 'measuring', 'recall': .9},
                         *({'status': 'frozen', 'recall': x} for x in
                           [None, True, -1, 1 - 1e-8, 1, 1.1, float('nan'), float('inf')])]:
            with self.subTest(baseline=baseline), self.assertRaises(ValueError):
                validate_reference(self.ref | {'recall_baseline': baseline})

    def test_query_count_required_for_error_resolution(self):
        for count in [None, 0, -1, True, 1.5]:
            with self.subTest(count=count), self.assertRaises(ValueError):
                validate_reference(self.ref | {'config': {'test_query_count': count}})

    def test_bad_memory_cannot_earn_bonus(self):
        for x in [0, -1, float('nan'), float('inf'), None]:
            with self.subTest(x=x), self.assertRaises(ValueError):
                dataset_score([{'rss_bytes': x, 'recall': 1, 'query_seconds': .1}] * 100, 1, self.ref)

    def test_no_reference_or_no_denominator(self):
        for change in [{'status': 'measuring'}, {'full_scan_seconds': [1.0]}, {'live_rss_bytes': [2 << 30] * 100}]:
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_reference(self.ref | change)

    def test_inflating_initial_memory_does_not_raise_score(self):
        a = dataset_score(self.stages, 2 << 30, self.ref)
        b = dataset_score(self.stages, 30 << 30, self.ref)
        self.assertEqual(a['reward'], b['reward'])

    def test_invalid_ids_not_replaced(self):
        result = {'query_id': 1, 'results': [{'id': i, 'distance': 0.} for i in [0, 0, 1, 55, -1, 2]]}
        self.assertEqual(recall(result, list(range(10)), [True, False] + [True] * 8, 1), .2)

    def test_query_failure_keeps_zero(self):
        for r in [None, {}, {'query_id': 1, 'results': [{}] * 11},
                  {'query_id': True, 'results': [{'id': 0, 'distance': 0}]},
                  {'query_id': 1, 'results': [{'id': 0, 'distance': float('nan')}]}]:
            self.assertEqual(recall(r, list(range(10)), [True] * 10, 1), 0.)


if __name__ == '__main__':
    unittest.main()
