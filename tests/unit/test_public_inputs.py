"""Public-input permissions survive restrictive checkout and cache modes."""

import json
import os
from pathlib import Path
import tempfile
import unittest

from scripts.evaluation.public_inputs import prepare_public_inputs


class PublicInputTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.task = Path(self.temporary.name)
        self.environment = self.task / "environment"
        self.environment.mkdir()
        (self.task / "task.toml").write_text("[metadata]\npublic_inputs_readable = true\n")
        self.starter = self.environment / "starter"
        self.starter.mkdir(mode=0o700)
        self.script = self.starter / "run.sh"
        self.script.write_text("#!/bin/sh\nexit 0\n")
        self.script.chmod(0o700)
        self.data = self.starter / "data.json"
        self.data.write_text("{}\n")
        self.data.chmod(0o600)
        self.mount = dict(type="bind", source=str(self.starter), target="/task/starter", read_only=True)
        self.document = {"services": {"main": {"volumes": [self.mount]}}}
        self.declare([{**self.mount, "source": "./starter"}])

    def declare(self, mounts):
        (self.environment / "docker-compose.yaml").write_text(json.dumps({"services": {"main": {"volumes": mounts}}}))

    def test_both_phases_fix_modes_without_changing_bytes_or_metadata(self):
        for phase in ("environment", "tests"):
            for path, mode in ((self.starter, 0o700), (self.script, 0o700), (self.data, 0o600)):
                path.chmod(mode)
            before = {p: (p.read_bytes(), p.stat().st_ino, p.stat().st_mtime_ns, p.stat().st_uid)
                      for p in (self.script, self.data)}
            prepare_public_inputs(self.document, self.task / phase)
            self.assertEqual(self.starter.stat().st_mode & 0o777, 0o755)
            self.assertEqual(self.script.stat().st_mode & 0o777, 0o755)
            self.assertEqual(self.data.stat().st_mode & 0o777, 0o644)
            for p, expected in before.items():
                self.assertEqual((p.read_bytes(), p.stat().st_ino, p.stat().st_mtime_ns, p.stat().st_uid), expected)
            prepare_public_inputs(self.document, self.task / phase)

    def test_hidden_inputs_and_writable_mounts_are_untouched(self):
        hidden = self.task / "tests"
        hidden.mkdir(mode=0o700)
        labels = hidden / "labels.json"
        labels.write_text("private"); labels.chmod(0o600)
        secret_mount = dict(type="bind", source=str(hidden), target="/task/private", read_only=True)
        self.document["services"]["main"]["volumes"].append(secret_mount)
        # Even an accidental declaration cannot select tests/ for chmod.
        self.declare([self.mount, secret_mount])
        prepare_public_inputs(self.document, hidden)
        self.assertEqual(hidden.stat().st_mode & 0o777, 0o700)
        self.assertEqual(labels.stat().st_mode & 0o777, 0o600)
        self.starter.chmod(0o700)
        self.mount["read_only"] = False
        prepare_public_inputs(self.document, hidden)
        self.assertEqual(self.starter.stat().st_mode & 0o777, 0o700)

    def test_verifier_only_public_looking_mount_is_not_selected(self):
        self.declare([])
        prepare_public_inputs(self.document, self.task / "tests")
        self.assertEqual(self.starter.stat().st_mode & 0o777, 0o700)

    def test_other_tasks_keep_their_existing_permission_policy(self):
        (self.task / "task.toml").write_text("[metadata]\n")
        prepare_public_inputs(self.document, self.environment)
        self.assertEqual(self.starter.stat().st_mode & 0o777, 0o700)

    def test_external_sources_and_wrong_targets_are_not_selected(self):
        for mount in ({**self.mount, "source": str(self.task.parent)},
                      {**self.mount, "target": "/tests"}):
            self.declare([mount])
            prepare_public_inputs({"services": {"main": {"volumes": [mount]}}}, self.environment)
            self.assertEqual(self.starter.stat().st_mode & 0o777, 0o700)

    def test_symlinks_hardlinks_and_special_files_fail_before_chmod(self):
        hidden = self.task / "secret"
        hidden.write_text("private"); hidden.chmod(0o600)
        link = self.starter / "link"
        for kind in ("symlink", "hardlink", "fifo"):
            if kind == "symlink":
                link.symlink_to(hidden)
            elif kind == "hardlink":
                os.link(hidden, link)
            else:
                os.mkfifo(link)
            try:
                with self.subTest(kind=kind), self.assertRaises(ValueError):
                    prepare_public_inputs(self.document, self.environment)
                self.assertEqual(hidden.stat().st_mode & 0o777, 0o600)
                self.assertEqual(self.starter.stat().st_mode & 0o777, 0o700)
            finally:
                link.unlink()

    def test_restored_assets_are_also_prepared(self):
        model = self.task / "models/base"
        model.mkdir(parents=True, mode=0o700)
        weights = model / "weights"
        weights.write_bytes(b"fixture"); weights.chmod(0o600)
        mount = dict(type="bind", source=str(model), target="/task/models", read_only=True)
        self.declare([{**mount, "source": "../models/base"}])
        prepare_public_inputs({"services": {"main": {"volumes": [mount]}}}, self.task / "tests")
        self.assertEqual(model.stat().st_mode & 0o777, 0o755)
        self.assertEqual(weights.stat().st_mode & 0o777, 0o644)


if __name__ == "__main__":
    unittest.main()
