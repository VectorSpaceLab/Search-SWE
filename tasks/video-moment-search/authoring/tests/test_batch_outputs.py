"""Regression coverage for recovering independent JSONL query results."""

import sys
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(TASK_ROOT / "tests"))


import json
import tempfile
import unittest

from batch_runtime import completed_rows


class QueryOutputTests(unittest.TestCase):
    def read_rows(self, text):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "results.jsonl"
            path.write_text(text, encoding="utf-8")
            return completed_rows(path)

    def test_bad_json_does_not_discard_surrounding_results(self):
        first, last = {"query_id": "first"}, {"query_id": "last"}
        text = json.dumps(first) + "\nBROKEN\n" + json.dumps(last) + "\n"
        self.assertEqual(self.read_rows(text), [first, last])

    def test_nonfinite_numbers_only_discard_the_affected_row(self):
        first, last = {"query_id": "first"}, {"query_id": "last"}
        for number in ("NaN", "Infinity", "-Infinity", "1e309", "-1e309"):
            for payload in ('{"score":' + number + '}',
                            '{"nested":[{"value":' + number + '}]}'):
                with self.subTest(number=number, payload=payload):
                    bad = '{"query_id":"bad","results":' + payload + '}'
                    text = json.dumps(first) + "\n" + bad + "\n" + json.dumps(last)
                    rows = self.read_rows(text)
                    self.assertEqual(rows, [first, {"query_id": "bad"}, last])
                    json.dumps(rows, allow_nan=False)

    def test_nonfinite_payload_keeps_duplicate_and_unknown_string_ids(self):
        valid = {"query_id": "duplicate", "results": []}
        text = json.dumps(valid) + '\n{"query_id":"duplicate","score":1e309}'
        text += '\n{"query_id":"unknown","nested":[NaN]}'
        self.assertEqual(self.read_rows(text),
                         [valid, {"query_id": "duplicate"}, {"query_id": "unknown"}])

    def test_nonfinite_nonstring_query_id_does_not_reach_diagnostic_output(self):
        valid = {"query_id": "valid"}
        text = '{"query_id":1e309}\n{"score":NaN}\n' + json.dumps(valid)
        rows = self.read_rows(text)
        self.assertEqual(rows, [valid])
        json.dumps(rows, allow_nan=False)

    def test_finite_numbers_and_integer_precision_are_preserved(self):
        row = {"query_id": "valid", "score": 1e308, "small": 1e-308,
               "count": 9007199254740993, "text": "NaN"}
        rows = self.read_rows(json.dumps(row))
        self.assertEqual(rows, [row])
        self.assertIsInstance(rows[0]["count"], int)
        json.dumps(rows, allow_nan=False)

    def test_large_integers_remain_available_for_individual_validation(self):
        rows = [{"query_id": "first"}, {"query_id": "large", "score": 10**400},
                {"query_id": "last"}]
        recovered = self.read_rows("\n".join(json.dumps(row) for row in rows))
        self.assertEqual(recovered, rows)
        # Integer precision is not limited by JSONL recovery. Numeric validation
        # handles conversion overflow per query; diagnostic writes remain safe.
        json.dumps(recovered, allow_nan=False)

    def test_unfinished_final_row_keeps_completed_results(self):
        row = {"query_id": "complete"}
        self.assertEqual(
            self.read_rows(json.dumps(row) + '\n{"query_id":"unfinished"'),
            [row],
        )

    def test_non_object_rows_do_not_discard_valid_results(self):
        row = {"query_id": "valid"}
        self.assertEqual(
            self.read_rows('[]\nnull\n"text"\n' + json.dumps(row) + "\n"),
            [row],
        )

    def test_duplicate_ids_remain_available_for_duplicate_checks(self):
        row = {"query_id": "duplicate"}
        self.assertEqual(
            self.read_rows((json.dumps(row) + "\n") * 2), [row, row]
        )

    def test_missing_output_has_no_completed_results(self):
        with tempfile.TemporaryDirectory() as temp:
            self.assertEqual(completed_rows(Path(temp) / "missing"), [])

    def test_symlink_is_not_read_as_output(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "results.jsonl"
            path.write_text('{"query_id":"not-readable-through-link"}\n')
            link = Path(temp) / "link"
            link.symlink_to(path)
            self.assertEqual(completed_rows(link), [])


if __name__ == "__main__":
    unittest.main()
