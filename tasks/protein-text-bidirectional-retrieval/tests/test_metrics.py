from pathlib import Path
import sys
import unittest

sys.path.insert(0, '/task/runtime' if Path('/task/runtime').is_dir() else
                str(Path(__file__).resolve().parents[1] / 'environment/runtime'))
from metrics import paired_quality, paired_top1, percentile, score, summarize


def records(ids, successful):
    return [{'query_id': x, 'valid': True, 'hit1': x in successful} for x in ids]


class MetricsTest(unittest.TestCase):
    def test_disjoint_directional_hits_give_no_mutual_success(self):
        pairs = {'p-A': 't-Z', 'p-B': 't-Y'}
        result = paired_top1(pairs, records(pairs, {'p-A'}), records(pairs.values(), {'t-Y'}))
        self.assertEqual(result['mutual_top1_correct'], 0)
        self.assertEqual(result['pairs'], 2)

    def test_intersection_uses_official_mapping_not_row_order(self):
        pairs = {'p-A': 't-Z', 'p-B': 't-Y'}
        result = paired_top1(pairs, records(['p-B', 'p-A'], {'p-A'}), records(['t-Y', 't-Z'], {'t-Z'}))
        self.assertEqual(result['mutual_top1_accuracy'], .5)

    def test_failed_queries_keep_pair_denominator(self):
        pairs = {'p-A': 't-Z', 'p-B': 't-Y'}
        backward = records(pairs.values(), set(pairs.values()))
        backward[0]['valid'] = False
        result = paired_top1(pairs, records(pairs, set(pairs)), backward)
        self.assertEqual(result['pairs'], 2)
        self.assertEqual(result['mutual_top1_correct'], 1)

    def test_missing_duplicate_or_nonbijective_queries_rejected(self):
        pairs = {'p-A': 't-Z', 'p-B': 't-Y'}
        good = records(pairs.values(), set())
        for forward in [records(['p-A'], set()), records(['p-A', 'p-A'], set()), records(['p-A', 'unknown'], set())]:
            with self.assertRaises(ValueError):
                paired_top1(pairs, forward, good)
        with self.assertRaises(ValueError):
            paired_top1({'p-A': 't-Z', 'p-B': 't-Z'}, records(pairs, set()), good)
        with self.assertRaises(ValueError):
            paired_top1({}, [], [])

    def test_macro_average_counts_each_dataset_equally(self):
        data = [{'pairs': 2, 'mutual_top1_correct': 1}, {'pairs': 4, 'mutual_top1_correct': 1}]
        self.assertEqual(paired_quality(data), .375)
        for bad in [data[:1], [{'pairs': 0, 'mutual_top1_correct': 0}] * 2,
                    [{'pairs': 2, 'mutual_top1_correct': 3}] * 2]:
            with self.assertRaises(ValueError):
                paired_quality(bad)

    def test_failure_denominator_and_latency(self):
        good = {'valid': True, 'hit20': True, 'hit1': False, 'seconds': .01}
        bad = {'valid': False, 'hit20': False, 'hit1': False, 'seconds': .0001}
        result = summarize([good] * 94 + [bad] * 6)
        self.assertEqual(result['recall_at_20'], .94)
        self.assertEqual(result['p95'], 3.)
        self.assertFalse(result['latency_gate'])
        self.assertEqual(summarize([good] * 95 + [bad] * 5)['p95'], .01)

    def test_nearest_rank(self):
        self.assertEqual(percentile(list(range(1, 10001)), .95), 9500)

    def test_score_is_direct_fraction_with_whole_group_gates(self):
        groups = [{'latency_gate': True}] * 4
        data = [{'pairs': 10000, 'mutual_top1_correct': 2000}] * 2
        self.assertEqual(score(groups, data), .2)
        self.assertEqual(score(groups, [{'pairs': 10000, 'mutual_top1_correct': 10000}] * 2), 1.)
        self.assertEqual(score(groups, [{'pairs': 10000, 'mutual_top1_correct': 0}] * 2), 0.)
        groups[2] = {'latency_gate': False}
        self.assertEqual(score(groups, data), 0.)
        self.assertEqual(score(groups[:3], data), 0.)


if __name__ == '__main__':
    unittest.main()
