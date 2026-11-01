"""Cache reuse, repair and storage estimates without remote asset downloads."""

import argparse
import hashlib
import os
import ssl
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.assets import asset_space, download_assets as assets


class AssetStorageTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.cache = self.root / "cache"
        self.content = b"immutable fixture model"
        self.entry = {"path": "models/weights.bin", "size_bytes": len(self.content),
                      "sha256": hashlib.sha256(self.content).hexdigest(),
                      "source": {"repo_id": "fixture/model", "repo_type": "model", "revision": "a" * 40,
                                 "filename": "weights.bin"}}
        self.cached = self.cache / "models--fixture--model" / "snapshots" / ("a" * 40) / "weights.bin"
        self.args = argparse.Namespace(force=True, verify_only=False, local_files_only=False, cache_dir=self.cache)
        self.records = [(self.root / name / self.entry["path"], self.entry) for name in ("first", "second")]

    def seed_cache(self, content=None):
        self.cached.parent.mkdir(parents=True, exist_ok=True)
        self.cached.write_bytes(self.content if content is None else content)

    def test_force_target_repair_reuses_real_hf_cache_across_tasks_without_network(self):
        self.seed_cache()
        with patch("httpx.Client.send", side_effect=AssertionError("unexpected network request")):
            for target, entry in self.records:
                task = target.parents[1]
                task.mkdir()
                self.assertEqual(assets.restore(task, task, entry, {}, self.args), "downloaded")
                self.assertEqual(target.read_bytes(), self.content)
        self.assertEqual(self.cached.read_bytes(), self.content)

    def test_corrupt_cache_is_refetched_once_and_verified(self):
        self.seed_cache(b"broken")
        calls = []
        def download(**kwargs):
            calls.append(kwargs["force_download"])
            if kwargs["force_download"]:
                self.cached.write_bytes(self.content)
            return str(self.cached)
        with patch("huggingface_hub.hf_hub_download", side_effect=download):
            self.assertEqual(assets.obtain_source(self.root, self.entry, self.args).read_bytes(), self.content)
        self.assertEqual(calls, [False, True])

    def test_corrupt_offline_cache_fails_without_forcing_a_download(self):
        self.seed_cache(b"broken")
        self.args.local_files_only = True
        with patch("huggingface_hub.hf_hub_download", return_value=str(self.cached)) as download:
            with self.assertRaisesRegex(ValueError, "retry without --local-files-only"):
                assets.obtain_source(self.root, self.entry, self.args)
        download.assert_called_once()
        self.assertFalse(download.call_args.kwargs["force_download"])

    def test_cache_repair_preserves_proxy_tls_retry(self):
        self.seed_cache(b"broken")
        valid = self.root / "repaired"
        valid.write_bytes(self.content)
        with patch.dict(os.environ, {"https_proxy": "http://127.0.0.1:7890"}, clear=True), \
                patch("huggingface_hub.hf_hub_download", side_effect=[str(self.cached),
                      ssl.SSLEOFError(8, "EOF occurred in violation of protocol"), str(valid)]) as download, \
                patch.object(assets, "configure_hf_tls12") as tls:
            self.assertEqual(assets.obtain_source(self.root, self.entry, self.args), valid)
        self.assertEqual([call.kwargs["force_download"] for call in download.call_args_list], [False, True, True])
        tls.assert_called_once()

    def test_shared_source_reserved_once_and_same_disk_needs_sum_of_copies_and_cache(self):
        size = len(self.content)
        with patch.object(asset_space, "filesystem", return_value=(1, size * 2)):
            plan = asset_space.plan(self.records, cache_dir=self.cache)
        self.assertEqual(plan["task_bytes"], size * 2)
        self.assertEqual(plan["task_additional_bytes"], size * 2)
        self.assertEqual(plan["cache_additional_bytes"], size)
        self.assertEqual(plan["filesystems"][0]["additional_bytes"], size * 3)
        with self.assertRaisesRegex(ValueError, "Insufficient asset storage"):
            asset_space.validate(plan)
        self.assertFalse(self.cache.exists())

    def test_existing_cache_and_task_copy_reduce_estimate_on_separate_disks(self):
        self.seed_cache()
        first, _ = self.records[0]
        first.parent.mkdir(parents=True)
        first.write_bytes(self.content)
        def disks(path):
            return (2, 1000) if Path(path) == self.cache else (1, 2000)
        with patch.object(asset_space, "filesystem", side_effect=disks):
            plan = asset_space.plan(self.records, cache_dir=self.cache)
        self.assertEqual(plan["task_additional_bytes"], len(self.content))
        self.assertEqual(plan["cache_additional_bytes"], 0)
        self.assertEqual(len(plan["filesystems"]), 2)
        asset_space.validate(plan)

    def test_replacement_estimate_includes_atomic_staging(self):
        self.seed_cache()
        target, entry = self.records[0]
        target.parent.mkdir(parents=True)
        target.write_bytes(b"x")
        plan = asset_space.plan([(target, entry)], cache_dir=self.cache)
        self.assertEqual(plan["task_additional_bytes"], len(self.content) - 1)
        self.assertEqual(plan["filesystems"][0]["additional_bytes"], len(self.content))


if __name__ == "__main__":
    unittest.main()
