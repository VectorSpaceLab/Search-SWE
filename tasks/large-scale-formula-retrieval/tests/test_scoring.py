import math
import unittest
from scoring import evaluate


class ScoringTests(unittest.TestCase):
    def score(self, ids, scores=None, qrels=None):
        return evaluate({'query_id': 'q', 'results': [
            {'formula_id': str(i), 'score': s} for i, s in zip(ids, scores or list(range(len(ids), 0, -1)))]},
            'q', [-1, 10, 10, 20, 30, 40], qrels or {10: 3, 20: 0, 30: 2})

    def test_duplicates_invalid_and_unjudged_are_removed(self):
        self.assertEqual(self.score([1, 2, 5, 100, 0, 4])['ndcg_prime'], 1.0)

    def test_zero_grade_keeps_rank(self):
        ideal = 3 + 2 / math.log2(3)
        self.assertAlmostEqual(self.score([3, 1, 4])['ndcg_prime'], (3 / math.log2(3) + 1) / ideal)

    def test_full_qrels_ideal_not_returned_subset(self):
        self.assertLess(self.score([1])['ndcg_prime'], 1)
        self.assertEqual(self.score([1])['map_prime'], .5)
        self.assertEqual(self.score([1])['p_prime_10'], .1)

    def test_score_sort_and_stable_ties(self):
        self.assertEqual(self.score([4, 1], [1, 2])['ndcg_prime'], 1)
        self.assertLess(self.score([4, 1], [1, 1])['ndcg_prime'], 1)

    def test_output_failures(self):
        self.assertFalse(self.score([1], [float('nan')])['valid'])
        self.assertFalse(self.score([1] * 1001)['valid'])
        self.assertFalse(evaluate({}, 'q', [], {1: 3})['valid'])
        self.assertEqual(self.score([])['ndcg_prime'], 0)
        self.assertFalse(self.score([1], [10 ** 1000])['valid'])
        self.assertEqual(self.score(['9' * 5000])['ndcg_prime'], 0)
        self.assertEqual(self.score(['0' * 5000 + '1'])['ndcg_prime'], self.score([1])['ndcg_prime'])


if __name__ == '__main__':
    unittest.main()
