import unittest
import numpy as np
from pathlib import Path
import sys

if Path(__file__).parent.name == 'tests':
    sys.path.insert(0, '/task/runtime' if Path('/task/runtime').is_dir() else
                    str(Path(__file__).resolve().parents[1] / 'environment/runtime'))

from ranker import DIMENSION, POOL_SIZE, Ranker, normalized


class RankingProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ids = [f'opaque-{i:05d}' for i in range(POOL_SIZE)]
        cls.values = np.random.default_rng(20261020).normal(size=(POOL_SIZE, DIMENSION))
        cls.ranker = Ranker(cls.ids, cls.values)

    def test_raw_matching_vector_retrieves_its_strict_id(self):
        for i in [0, 47, 5031, 9999]:
            self.assertEqual(self.ranker.search(self.values[i])[0], self.ids[i])

    def test_positive_rescaling_preserves_rank(self):
        expected = self.ranker.search(self.values[93])
        self.assertEqual(self.ranker.search(70 * self.values[93]), expected)

    def test_equal_vectors_keep_distinct_ids_and_stable_ties(self):
        values = np.ones((POOL_SIZE, DIMENSION))
        ranker = Ranker(self.ids[::-1], values)
        self.assertEqual(ranker.search(np.ones(DIMENSION)), self.ids[:20])

    def test_wrong_dimension_and_nonnumeric_vectors_rejected(self):
        for value in [np.zeros(63), np.zeros((1, 64)), ['1'] * 64, [True] * 64]:
            with self.assertRaises(ValueError):
                self.ranker.search(value)

    def test_nonfinite_and_float32_overflow_rejected(self):
        for value in [np.full(64, np.nan), np.full(64, np.inf), np.full(64, 1e100)]:
            with self.assertRaises(ValueError):
                self.ranker.search(value)

    def test_large_legal_values_normalize_without_overflow(self):
        value = normalized(np.full(64, 3e38), (64,))
        self.assertTrue(np.isfinite(value).all())
        self.assertAlmostEqual(float(np.linalg.norm(value)), 1.0, places=6)

    def test_zero_or_none_abstains(self):
        self.assertEqual(self.ranker.search(None), [])
        self.assertEqual(self.ranker.search(np.zeros(64)), [])

    def test_bad_pool_or_duplicate_ids_rejected(self):
        for ids, vectors in [(self.ids[:-1], self.values[:-1]),
                             ([self.ids[0]] * POOL_SIZE, self.values),
                             (self.ids, np.zeros((POOL_SIZE, 65)))]:
            with self.assertRaises(ValueError):
                Ranker(ids, vectors)


if __name__ == '__main__':
    unittest.main()
