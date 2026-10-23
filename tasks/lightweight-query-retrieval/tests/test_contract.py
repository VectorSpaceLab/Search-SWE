import copy
import math
import unittest

from scoring import VerificationError, strict_json, validate_response, ndcg_at_10, quality, speed_reward
from grader import MINIMUM_QUALITY, FAST_SECONDS, SLOW_SECONDS


class Contract(unittest.TestCase):
    def setUp(self):
        self.corpus = {"a": ("first", 0), "b": ("first", 1), "c": ("second", 2)}
        self.queries = [{"query_id": "q1", "collection": "first"}, {"query_id": "q2", "collection": "second"}]
        self.response = {"results": [
            {"query_id": "q1", "results": [{"doc_id": "a", "score": 2}, {"doc_id": "b", "score": 1}]},
            {"query_id": "q2", "results": [{"doc_id": "c", "score": .5}]}]}

    def test_valid_reordered_queries(self):
        self.response["results"].reverse()
        self.assertEqual(validate_response(self.response, self.queries, self.corpus), {"q2": ["c"], "q1": ["a", "b"]})

    def test_original_linear_grades(self):
        actual = ndcg_at_10(["b", "a"], {"a": 2, "b": 1})
        self.assertAlmostEqual(actual, (1+2/math.log2(3))/(2+1/math.log2(3)))
        self.assertEqual(ndcg_at_10([], {"a": 1}), 0)
        self.assertEqual(ndcg_at_10(["a", "b"], {"a": 2, "b": 1}), 1)

    def test_all_positives_in_ideal(self):
        self.assertLess(ndcg_at_10(["a"], {"a": 1, "b": 1}), 1)

    def test_equal_collection_weight(self):
        predictions = {"x": ["a"], "y": ["a"], "z": []}
        gold = {"x": {"collection": "first", "relevance": {"a": 1}},
                "y": {"collection": "first", "relevance": {"a": 1}},
                "z": {"collection": "second", "relevance": {"b": 1}}}
        self.assertEqual(quality(predictions, gold)[0], .5)

    def test_gate_and_linear_time_score(self):
        bounds = (MINIMUM_QUALITY, FAST_SECONDS, SLOW_SECONDS)
        self.assertEqual(bounds, (.45, 0., .8))
        self.assertEqual(speed_reward(math.nextafter(.45, 0), 0, *bounds), 0)
        self.assertEqual(speed_reward(.45, 0, *bounds), 1)
        self.assertLess(speed_reward(.45, 1e-9, *bounds), 1)
        self.assertAlmostEqual(speed_reward(.45, .4, *bounds), .5)
        self.assertAlmostEqual(speed_reward(.8, .5, *bounds), .375)
        self.assertGreater(speed_reward(.8, math.nextafter(.8, 0), *bounds), 0)
        self.assertEqual(speed_reward(.8, .8, *bounds), 0)
        self.assertEqual(speed_reward(.8, 1, *bounds), 0)

    def test_invalid_times(self):
        for value in (-1, float("nan"), float("inf"), True):
            with self.assertRaises(VerificationError):
                speed_reward(.8, value, MINIMUM_QUALITY, FAST_SECONDS, SLOW_SECONDS)

    def test_coverage(self):
        for rows in ([], self.response["results"][:1], self.response["results"]*2):
            with self.assertRaises(VerificationError):
                validate_response({"results": rows}, self.queries, self.corpus)

    def test_cross_collection(self):
        self.response["results"][0]["results"][0]["doc_id"] = "c"
        with self.assertRaises(VerificationError):
            validate_response(self.response, self.queries, self.corpus)

    def test_invalid_scores(self):
        for score in (float("nan"), float("inf"), "1", None, True, 10**1000):
            data = copy.deepcopy(self.response)
            data["results"][0]["results"][0]["score"] = score
            with self.assertRaises(VerificationError):
                validate_response(data, self.queries, self.corpus)

    def test_duplicate_unknown_documents(self):
        for doc in ("a", "missing", 1):
            data = copy.deepcopy(self.response)
            data["results"][0]["results"][1]["doc_id"] = doc
            with self.assertRaises(VerificationError):
                validate_response(data, self.queries, self.corpus)

    def test_ranking_and_ties(self):
        self.response["results"][0]["results"][1]["score"] = 2
        validate_response(self.response, self.queries, self.corpus)
        self.response["results"][0]["results"].reverse()
        validate_response(self.response, self.queries, self.corpus)
        self.response["results"][0]["results"][1]["score"] = 3
        with self.assertRaises(VerificationError):
            validate_response(self.response, self.queries, self.corpus)

    def test_ambiguous_json(self):
        for text in ('{"a":1,"a":2}', '{"a":NaN}', '{"a":Infinity}'):
            with self.assertRaises(VerificationError):
                strict_json(text)


if __name__ == "__main__":
    unittest.main()
