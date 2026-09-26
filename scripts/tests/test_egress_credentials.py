import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.tests.egress_credentials import CredentialLeak, CredentialProbe


class CredentialEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.TemporaryDirectory()
        self.addCleanup(self.root.cleanup)
        patched = patch("scripts.tests.egress_credentials.owner_root", return_value=Path(self.root.name))
        patched.start()
        self.addCleanup(patched.stop)
        self.probe = CredentialProbe()
        self.addCleanup(self.probe.close)

    def test_raw_json_url_and_basic_variants_are_detected_without_echo(self):
        for pattern in self.probe.patterns:
            with self.subTest(), self.assertRaises(CredentialLeak) as caught:
                self.probe.scan(b"prefix=" + pattern, "fixture-surface")
            for value in self.probe.auth.values():
                self.assertNotIn(value, str(caught.exception))

    def test_private_source_is_owner_only_and_removed(self):
        self.assertEqual(self.probe.path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.probe.path.parent.stat().st_mode & 0o777, 0o700)
        self.assertEqual(json.loads(self.probe.path.read_text()), self.probe.auth)
        self.probe.close()
        self.assertFalse(self.probe.path.exists())

    def test_artifact_hit_is_withheld_not_reported_as_clean(self):
        root = Path(self.root.name) / "output"
        root.mkdir()
        artifact = root / "leaking-fixture.log"
        artifact.write_text(json.dumps(self.probe.auth))
        with self.assertRaises(CredentialLeak):
            self.probe.artifacts(root)
        self.assertIn("Withheld", artifact.read_text())
        self.probe.scan(artifact.read_bytes(), "sanitized-fixture")

    def test_external_source_is_not_deleted_by_child_probe(self):
        child = CredentialProbe(self.probe.path)
        child.close()
        self.assertTrue(self.probe.path.exists())

    def test_safe_artifacts_pass_and_symlinks_are_rejected(self):
        root = Path(self.root.name) / "output"
        root.mkdir()
        (root / "safe.json").write_text('{"kind":"generation_ready"}')
        self.probe.artifacts(root)
        (root / "unsafe-link").symlink_to(self.probe.path)
        with self.assertRaisesRegex(RuntimeError, "symlink"):
            self.probe.artifacts(root)
