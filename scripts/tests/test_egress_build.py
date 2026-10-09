import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from scripts.build_egress_gateway import stage_archives
from scripts.egress.build_audit import collect_notices, json_stream, runtime_inventory


class RuntimeBuildTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.cache = self.root / "cache"
        self.cache.mkdir()
        self.payload = b"fixture-only-archive"
        self.lock = {"archives": {"fixture.apk": hashlib.sha256(self.payload).hexdigest()}}

    def test_missing_archive_does_not_silently_download(self):
        with self.assertRaisesRegex(ValueError, "--download explicitly"):
            stage_archives(self.lock, self.cache, self.root / "context")

    def test_corrupt_cache_is_rejected(self):
        (self.cache / "fixture.apk").write_bytes(b"corrupt")
        with self.assertRaisesRegex(ValueError, "checksum mismatch"):
            stage_archives(self.lock, self.cache, self.root / "context")

    def test_valid_cache_is_copied_without_mutation(self):
        (self.cache / "fixture.apk").write_bytes(self.payload)
        stage_archives(self.lock, self.cache, self.root / "context")
        self.assertEqual((self.root / "context/fixture.apk").read_bytes(), self.payload)
        self.assertEqual((self.cache / "fixture.apk").read_bytes(), self.payload)

    def test_archive_path_traversal_is_rejected(self):
        self.lock["archives"] = {"../fixture.apk": "invalid"}
        with self.assertRaisesRegex(ValueError, "filename"):
            stage_archives(self.lock, self.cache, self.root / "context")


class BuildAuditTests(unittest.TestCase):
    def test_go_json_stream(self):
        self.assertEqual(list(json_stream(' {"Path":"a"}\n{"Path":"b"} ')), [{"Path": "a"}, {"Path": "b"}])
        with self.assertRaises(json.JSONDecodeError):
            list(json_stream('{"Path":'))

    def test_only_linked_modules_but_nested_notices_are_retained(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name in ("main", "dependency", "go"):
                directory = root / name
                directory.mkdir()
                (directory / "LICENSE").write_text("fixture license\n")
            (root / "dependency/nested").mkdir()
            (root / "dependency/nested/NOTICE.txt").write_text("nested notice\n")
            info = {"Main": {"Path": "example/main"}, "GoVersion": "fixture-go", "Deps": [{"Path": "example/dep", "Version": "v1"}]}
            modules = [{"Path": "example/main", "Dir": str(root / "main")},
                       {"Path": "example/dep", "Replace": {"Dir": str(root / "dependency")}},
                       {"Path": "example/not-linked", "Dir": "/absent"}]
            manifest = collect_notices(info, modules, root / "go", root / "notices")
            self.assertEqual(len(manifest["modules"]), 3)
            self.assertEqual(sum(len(m["notices"]) for m in manifest["modules"]), 4)
            self.assertTrue((root / "notices/index.json").is_file())

    def test_missing_license_and_symlink_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            module = root / "module"
            module.mkdir()
            info = {"Main": {"Path": "example/main"}, "GoVersion": "fixture-go"}
            modules = [{"Path": "example/main", "Dir": str(module)}]
            with self.assertRaisesRegex(ValueError, "no collected license"):
                collect_notices(info, modules, root, root / "attempt1")
            (module / "LICENSE").symlink_to(root / "somewhere")
            with self.assertRaisesRegex(ValueError, "notice file"):
                collect_notices(info, modules, root, root / "attempt2")

    def test_runtime_inventory_requires_declared_license_and_origin(self):
        fields = "P:fixture\nV:1-r0\nL:MIT\no:fixture\nc:commit\nU:https://example.invalid\n"
        row = runtime_inventory(fields)["packages"][0]
        self.assertEqual(row["license_declared"], "MIT")
        self.assertEqual(row["aports_commit"], "commit")
        with self.assertRaisesRegex(ValueError, "Incomplete"):
            runtime_inventory("P:fixture\nV:1-r0\n")
