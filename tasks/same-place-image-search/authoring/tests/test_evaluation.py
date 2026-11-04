
import sys
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(TASK_ROOT / "tests"))

import unittest, math
from evaluation import quality, validate, aggregate


class Tests(unittest.TestCase):
    def test_ideal(self):
        self.assertEqual(quality(["a", "b"], {"a": 1, "b": 1}, []), 1)

    def test_junk_ignored(self):
        self.assertEqual(quality(["x", "a"], {"a": 1}, ["x"]), 1)

    def test_wrong_place(self):
        self.assertEqual(quality(["x"], {"a": 1}, []), 0)

    def test_rank(self):
        self.assertAlmostEqual(quality(["x", "a"], {"a": 1}, []), 1 / math.log2(3))

    def test_valid(self):
        self.assertEqual(
            validate(
                {"query_id": "q"},
                {"query_id": "q", "results": [{"image_id": "a", "score": 1}]},
                {"a": {}},
            ),
            ["a"],
        )

    def test_duplicate(self):
        with self.assertRaises(ValueError):
            validate(
                {"query_id": "q"},
                {"query_id": "q", "results": [{"image_id": "a", "score": 1}] * 2},
                {"a": {}},
            )

    def test_invalid_image_id_types_are_query_validation_errors(self):
        for image_id in [[], {}, None, 1, True]:
            with self.subTest(image_id=image_id), self.assertRaises(ValueError):
                validate(
                    {"query_id": "bad"},
                    {"query_id": "bad", "results": [{"image_id": image_id, "score": 1}]},
                    {"a": {}},
                )
        self.assertEqual(
            validate(
                {"query_id": "good"},
                {"query_id": "good", "results": [{"image_id": "a", "score": 1}]},
                {"a": {}},
            ),
            ["a"],
        )

    def test_macro(self):
        self.assertEqual(
            aggregate(
                [{"domain": "a", "value": 1}] * 3 + [{"domain": "b", "value": 0}]
            )[0],
            0.5,
        )


class HardGalleryTests(unittest.TestCase):
    def test_excluded_is_not_returnable(self):
        with self.assertRaises(ValueError):
            validate(
                {"query_id": "q", "exclude_image_ids": ["a"]},
                {"query_id": "q", "results": [{"image_id": "a", "score": 1}]},
                {"a": {}},
            )

    def test_eligible_hard_result(self):
        self.assertEqual(
            validate(
                {"query_id": "q", "exclude_image_ids": ["b"]},
                {"query_id": "q", "results": [{"image_id": "a", "score": 1}]},
                {"a": {}, "b": {}},
            ),
            ["a"],
        )
