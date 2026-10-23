import math
import unittest
import numpy as np
from metrics import ndcg10, reward, valid_ranking
from oracle import Oracle, QueryFailure


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.now = 0.0
        self.oracle = Oracle(np.array([[0, 0], [3, 4]], dtype='f4'), clock=lambda: self.now)
        self.oracle.begin([0, 0], 'current', 2.0)

    def score(self, ids, token='current'):
        return self.oracle.score({'op': 'score', 'token': token, 'doc_ids': ids})

    def test_distances_and_duplicate_charges(self):
        response = self.score(['doc1', 'doc1', 'doc0'])
        self.assertEqual(response['distances'], [5, 5, 0])
        self.assertEqual(response['used'], 3)
        self.score(['doc0'] * 197)
        with self.assertRaisesRegex(QueryFailure, 'budget'):
            self.score(['doc0'])

    def test_cross_query_and_failure_latching(self):
        with self.assertRaises(QueryFailure): self.score(['doc0'], 'future')
        with self.assertRaises(QueryFailure): self.score(['doc0'])
        self.oracle.begin([3, 4], 'next', 2)
        self.assertEqual(self.score(['doc1'], 'next')['used'], 1)

    def test_reduced_budget_and_reset(self):
        self.oracle = Oracle(np.array([[0, 0], [3, 4]], dtype='f4'), budget=20, clock=lambda: self.now)
        self.oracle.begin([0, 0], 'current', 2)
        self.assertEqual(self.score(['doc0'] * 20)['remaining'], 0)
        with self.assertRaisesRegex(QueryFailure, 'budget'):
            self.score(['doc1'])
        with self.assertRaises(QueryFailure):
            self.score(['doc0'])
        self.oracle.begin([0, 0], 'current', 2)
        self.assertEqual(self.score(['doc1'])['remaining'], 19)

    def test_build_phase_denied(self):
        self.oracle.close()
        with self.assertRaises(QueryFailure): self.score(['doc0'])

    def test_deadline(self):
        self.now = 2.001
        with self.assertRaises(QueryFailure): self.score(['doc0'])

    def test_invalid_ids_and_vectors(self):
        for ids in [['doc2'], ['doc-1'], ['doc01'], ['doc²'], ['doc١'], ['doc'+'9'*5000], [False], [], 'doc0']:
            self.oracle.begin([0, 0], 'current', 2)
            with self.assertRaises(QueryFailure): self.score(ids)
        with self.assertRaises(ValueError): self.oracle.begin([float('nan'), 0], 'a', 2)

    def test_no_arbitrary_query(self):
        with self.assertRaises(QueryFailure):
            self.oracle.score({'op': 'score', 'token': 'current', 'doc_ids': ['doc0'], 'query': [0, 0]})

    def test_full_qrels_idcg(self):
        self.assertAlmostEqual(ndcg10(['doc1'], {'doc1': 1, 'doc2': 1}), 1/(1+1/math.log2(3)))
        self.assertEqual(ndcg10([], {'doc1': 1}), 0)

    def test_mean_before_mapping(self):
        self.assertAlmostEqual(reward((0.2+0.8)/2, 0.4, 0.6), .5)
        self.assertEqual(reward(.3,.4,.6),0)
        self.assertEqual(reward(.9,.4,.6),1)
        for b,u in [(None,None),(.5,.5),(.6,.5),(math.nan,.6)]:
            with self.assertRaises(ValueError): reward(.5,b,u)

    def test_rank_validity(self):
        self.assertTrue(valid_ranking([], 2))
        self.assertTrue(valid_ranking(['doc1','doc0'], 2))
        for ids in [['doc0','doc0'],['doc2'],['doc00'],['doc²'],['doc١'],['doc'+'9'*5000],['doc0']*11,{},None,[1]]:
            self.assertFalse(valid_ranking(ids,2))


if __name__ == '__main__': unittest.main()
