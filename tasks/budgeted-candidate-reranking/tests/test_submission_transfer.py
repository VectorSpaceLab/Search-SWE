"""Exercise the archive boundary used when Docker cannot copy a live tmpfs."""
import io
import os
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent / 'runtime'))
import submission_transfer as transfer


class SubmissionTransferTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'source'
        self.source.mkdir()
        self.archive = self.root / 'submission.tar'
        self.destination = self.root / 'restored'

    def malicious(self, member):
        with tarfile.open(self.archive, 'w') as tf:
            tf.addfile(member, io.BytesIO(b'x' * member.size) if member.isfile() else None)
        with self.assertRaises(ValueError):
            transfer.restore(self.archive, self.destination)
        self.assertFalse(self.destination.exists())

    def test_regular_files_modes_and_internal_hardlinks(self):
        p = self.source / 'run.sh'
        p.write_bytes(b'#!/bin/sh\nexit 0\n')
        p.chmod(0o755)
        os.link(p, self.source / 'linked')
        transfer.pack(self.source, self.archive)
        transfer.restore(self.archive, self.destination)
        self.assertEqual((self.destination/'run.sh').read_bytes(), p.read_bytes())
        self.assertEqual((self.destination/'linked').stat().st_ino,
                         (self.destination/'run.sh').stat().st_ino)
        self.assertTrue((self.destination/'run.sh').stat().st_mode & 0o100)
        self.assertFalse(self.archive.exists())

    def test_reject_root_link_and_remove_stale_archive(self):
        link = self.root / 'alias'
        link.symlink_to(self.source, target_is_directory=True)
        self.archive.write_bytes(b'stale')
        with self.assertRaises(ValueError):
            transfer.pack(link, self.archive)
        self.assertFalse(self.archive.exists())

    def test_reject_source_link_without_publishing_partial_archive(self):
        (self.source/'a').write_text('ordinary')
        (self.source/'z').symlink_to('/etc/passwd')
        with self.assertRaises(ValueError):
            transfer.pack(self.source, self.archive)
        self.assertFalse(self.archive.exists())

    def test_reject_absolute_and_parent_paths(self):
        for name in ['/etc/passwd', '../outside']:
            with self.subTest(name=name):
                self.malicious(tarfile.TarInfo(name))

    def test_reject_symlink_device_and_external_hardlink(self):
        for kind in [tarfile.SYMTYPE, tarfile.CHRTYPE, tarfile.LNKTYPE]:
            member = tarfile.TarInfo('bad')
            member.type, member.linkname = kind, '../outside'
            with self.subTest(kind=kind):
                self.malicious(member)

    def test_reject_oversized_contents_before_extracting(self):
        (self.source/'file').write_bytes(b'xx')
        transfer.pack(self.source, self.archive)
        with patch.object(transfer, 'WORKSPACE_BYTES', 1), self.assertRaises(ValueError):
            transfer.restore(self.archive, self.destination)
        self.assertFalse(self.destination.exists())
        with patch.object(transfer, 'WORKSPACE_BYTES', 1), self.assertRaises(ValueError):
            transfer.pack(self.source, self.archive)
        self.assertFalse(self.archive.exists())

    def test_reject_duplicate_members(self):
        with tarfile.open(self.archive, 'w') as tf:
            tf.addfile(tarfile.TarInfo('file'))
            tf.addfile(tarfile.TarInfo('file'))
        with self.assertRaises(ValueError):
            transfer.restore(self.archive, self.destination)
        self.assertFalse(self.destination.exists())


if __name__ == '__main__':
    unittest.main()
