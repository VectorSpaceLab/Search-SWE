import argparse
import hashlib
import importlib.util
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "download_assets.py"
spec = importlib.util.spec_from_file_location("download_assets", SCRIPT)
assets = importlib.util.module_from_spec(spec)
spec.loader.exec_module(assets)


class Downloads(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.task = self.root / "package"
        self.task.mkdir()
        self.output = self.root / "output"
        self.content = b"frozen model metadata\n"
        (self.task / "metadata.json").write_bytes(self.content)
        self.entry = {
            "path": "models/example/config.json",
            "size_bytes": len(self.content),
            "sha256": hashlib.sha256(self.content).hexdigest(),
            "source": {"local_path": "metadata.json"},
        }
        self.args = argparse.Namespace(verify_only=False, force=False, local_files_only=False, cache_dir=None)

    def restore(self, **kwargs):
        return assets.restore(self.task, self.output, kwargs.get("entry", self.entry), kwargs.get("modes", {}), self.args)

    def test_bundled_metadata_restored_and_repeated_run_skips_source(self):
        self.assertEqual(self.restore(), "restored metadata")
        target = self.output / self.entry["path"]
        self.assertEqual(target.read_bytes(), self.content)
        with patch.object(assets, "obtain_source", side_effect=AssertionError("must skip")):
            self.assertEqual(self.restore(), "verified")

    def test_valid_download_uses_exact_revision(self):
        source = {"repo_id": "owner/model", "repo_type": "model", "revision": "a" * 40, "filename": "config.json"}
        self.entry["source"] = source
        with patch("huggingface_hub.hf_hub_download", return_value=str(self.task / "metadata.json")) as download:
            self.assertEqual(self.restore(), "downloaded")
        for key, value in source.items():
            self.assertEqual(download.call_args.kwargs[key], value)

    def test_unpublished_revision_never_uses_main(self):
        self.entry["source"] = {"repo_id": "owner/data", "repo_type": "dataset", "revision": None, "filename": "data.json"}
        with patch("huggingface_hub.hf_hub_download") as download:
            with self.assertRaisesRegex(ValueError, "No published fixed revision"):
                self.restore()
        download.assert_not_called()

    def test_corrupt_download_preserves_existing_file_and_cleans_temporary(self):
        self.restore()
        target = self.output / self.entry["path"]
        target.write_bytes(b"existing data")
        bad = self.task / "bad"
        bad.write_bytes(b"corrupt network content")
        self.args.force = True
        with patch.object(assets, "obtain_source", return_value=bad):
            with self.assertRaisesRegex(ValueError, "verification"):
                self.restore()
        self.assertEqual(target.read_bytes(), b"existing data")
        self.assertEqual(list(target.parent.glob(".download-*")), [])

    def test_changed_existing_file_requires_force(self):
        self.restore()
        target = self.output / self.entry["path"]
        target.write_bytes(b"different")
        with self.assertRaisesRegex(ValueError, "--force"):
            self.restore()
        self.args.force = True
        self.restore()
        self.assertEqual(target.read_bytes(), self.content)

    def test_verify_only_never_downloads_or_changes_permissions(self):
        self.restore()
        target = self.output / self.entry["path"]
        target.chmod(0o600)
        self.args.verify_only = True
        with patch.object(assets, "obtain_source", side_effect=AssertionError("offline")):
            self.assertEqual(self.restore(), "verified")
            self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)
            target.unlink()
            with self.assertRaisesRegex(ValueError, "Missing or invalid"):
                self.restore()

    def test_private_reference_model_permissions(self):
        self.entry["mode"] = "0600"
        self.restore(modes={"models/example": "0700"})
        target = self.output / self.entry["path"]
        self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(target.parent.stat().st_mode), 0o700)

    def test_path_traversal_and_external_symlinks_are_rejected(self):
        for value in ("../outside", "/absolute", "data/../../outside"):
            with self.assertRaises(ValueError):
                assets.relative_path(value)
        (self.output / "models").mkdir(parents=True)
        (self.output / "models/example").symlink_to(self.task, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "inside"):
            self.restore()


if __name__ == "__main__":
    unittest.main()
