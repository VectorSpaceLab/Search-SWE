"""Verify sampled-source provenance and the downloadable-asset size contract."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

TASK = Path(__file__).resolve().parents[1]


class SampledDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # RewardKit imports this module while discovering the runtime judge.
        # Authoring inputs are needed only when these unit tests actually run.
        spec = importlib.util.spec_from_file_location("task_prepare_data", TASK / "prepare_data.py")
        cls.prepare = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.prepare)

    def test_downloaded_sources_fit_decimal_five_gigabytes(self):
        files = json.loads((TASK / "assets.json").read_text())["files"]
        self.assertLess(sum(f["size_bytes"] for f in files), 5_000_000_000)
        self.assertEqual(len(files), 12)

    def test_source_sampling_is_reproducible_without_replacement(self):
        prepare = self.prepare
        first = prepare.source_order(180, 120)
        np.testing.assert_array_equal(first, prepare.source_order(180, 120))
        self.assertEqual(len(set(first.tolist())), 120)
        self.assertTrue(np.all((0 <= first) & (first < 180)))
        with self.assertRaisesRegex(ValueError, "too few"):
            prepare.source_order(119, 120)

    def test_selected_vectors_and_disjoint_roles_retain_source_identity(self):
        prepare = self.prepare
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            physical = np.arange(16_000, dtype=np.float32)
            vectors = np.column_stack([physical, physical + .25])
            source = root / "data/upstream/2/fixture.parquet"
            source.parent.mkdir(parents=True)
            pq.write_table(pa.table({"text-embedding-3-large-2-embedding":
                                    pa.array(vectors.tolist())}), source)
            entry = {"path": str(source.relative_to(root)),
                     "size_bytes": source.stat().st_size,
                     "sha256": hashlib.sha256(source.read_bytes()).hexdigest()}
            (root / "assets.json").write_text(json.dumps({"files": [entry]}))
            with patch.multiple(prepare, ROOT=root, COUNT=12_040, INITIAL=12_020,
                                BATCH=2, STAGES=5):
                prepare.prepare(2)
            rows = np.load(root / "data/private/2/source_rows.npy")
            self.assertEqual(len(set(rows.tolist())), 12_040)
            outputs = [np.load(root / path) for path in
                       ["data/public/2/initial.npy", "data/private/2/inserts.npy",
                        "data/private/2/queries.npy"]]
            self.assertEqual([len(a) for a in outputs], [12_020, 10, 10])
            np.testing.assert_array_equal(np.concatenate(outputs), vectors[rows])
            selected = set(prepare.source_order(16_000, 12_040).tolist())
            self.assertEqual(set(rows.tolist()), selected)
            manifest = json.loads((root / "data/private/2/derived-manifest.json").read_text())
            self.assertEqual(manifest["available_source_rows"], 16_000)
            for item in manifest["files"]:
                self.assertEqual(prepare.digest(root / item["path"]), item["sha256"])


if __name__ == "__main__":
    unittest.main()
