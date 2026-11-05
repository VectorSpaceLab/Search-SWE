import copy
from pathlib import Path
import unittest

from repetition import REPEATS, median_result


def attempt(seconds, quality=0.7, valid=True):
    return {'seconds': seconds, 'valid': valid, 'ndcg_prime': quality,
            'map_prime': quality, 'p_prime_10': quality}


class RepetitionTests(unittest.TestCase):
    def test_median_time_selects_its_response_not_the_best_score(self):
        attempts = [attempt(.04, 1), attempt(.01, .9), attempt(.03, .4),
                    attempt(.02, .8), attempt(.045, .7)]
        result = median_result(attempts)
        self.assertEqual(result['seconds'], .03)
        self.assertEqual(result['ndcg_prime'], .4)
        self.assertEqual(result['median_repeat'], 3)

    def test_two_timeouts_do_not_override_three_valid_measurements(self):
        attempts = [attempt(.06, 1), attempt(.01), attempt(.02),
                    {'valid': False, 'error': 'timeout'}, attempt(.03)]
        result = median_result(attempts)
        self.assertTrue(result['valid'])
        self.assertEqual(result['successful_attempts'], 3)
        self.assertEqual(result['seconds'], .03)

    def test_three_failures_make_the_query_zero(self):
        result = median_result([attempt(.01), attempt(.02), attempt(.06),
                                attempt(.001, valid=False), {'error': 'launch failed'}])
        self.assertFalse(result['valid'])
        self.assertIsNone(result['seconds'])
        self.assertEqual(result['ndcg_prime'], 0)

    def test_invalid_fast_response_is_not_a_successful_timing(self):
        result = median_result([attempt(.001, 1, False), attempt(.01, .1),
                                attempt(.02, .2), attempt(.03, .3), attempt(.04, .4)])
        self.assertEqual(result['seconds'], .03)
        self.assertEqual(result['ndcg_prime'], .3)

    def test_ties_use_repeat_order(self):
        result = median_result([attempt(.01, quality) for quality in (.9, .8, .3, .7, .6)])
        self.assertEqual(result['median_repeat'], 3)
        self.assertEqual(result['ndcg_prime'], .3)

    def test_nonfinite_negative_and_boolean_times_are_not_valid(self):
        for seconds in (float('nan'), float('inf'), -.1, True, '0.01'):
            with self.subTest(seconds=seconds):
                result = median_result([attempt(seconds)] * 3 + [attempt(.01)] * 2)
                self.assertFalse(result['valid'])

    def test_exact_deadline_is_allowed(self):
        self.assertTrue(median_result([attempt(.05)] * REPEATS)['valid'])

    def test_requires_five_attempts_without_modifying_them(self):
        for count in (0, 1, 4, 6):
            with self.assertRaises(ValueError):
                median_result([attempt(.01)] * count)
        attempts = [attempt(.01)] * REPEATS
        original = copy.deepcopy(attempts)
        median_result(attempts)
        self.assertEqual(attempts, original)

    def test_public_and_private_aggregation_agree(self):
        private = Path(__file__).with_name('repetition.py')
        public = private.parent.parent / 'environment/tools/repetition.py'
        if not public.exists():
            self.skipTest('Public helper is outside the verifier build context')
        self.assertEqual(private.read_bytes(), public.read_bytes())


if __name__ == '__main__':
    unittest.main()
