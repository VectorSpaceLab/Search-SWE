import io
import os
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'environment/runtime'))
from submission_transfer import pack,restore,SUBMISSION_BYTES

class TransferTests(unittest.TestCase):
    def test_limit_boundary_and_sparse_logical_size(self):
        with tempfile.TemporaryDirectory() as d:
            d=Path(d);source=d/'source';source.mkdir()
            with (source/'weights').open('wb') as f:f.truncate(SUBMISSION_BYTES)
            pack(source,d/'archive');restore(d/'archive',d/'restored')
            self.assertEqual((d/'restored/weights').stat().st_size,SUBMISSION_BYTES)
            (source/'extra.py').write_text('x')
            with self.assertRaisesRegex(ValueError,'256 KiB'):pack(source,d/'archive')
            self.assertFalse((d/'archive').exists())
    def test_hardlinks_count_each_path_in_collection_and_restore(self):
        with tempfile.TemporaryDirectory() as d:
            d=Path(d);source=d/'source';source.mkdir()
            with (source/'weights').open('wb') as f:f.truncate(SUBMISSION_BYTES//2+1)
            os.link(source/'weights',source/'copy')
            with self.assertRaisesRegex(ValueError,'256 KiB'):pack(source,d/'archive')
            with tarfile.open(d/'archive','w') as tf:tf.add(source,arcname='.')
            with self.assertRaisesRegex(ValueError,'256 KiB'):restore(d/'archive',d/'restored')
    def test_real_archive_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            d=Path(d);source=d/'source';source.mkdir();(source/'encoder.py').write_text('example')
            pack(source,d/'submission.tar');restore(d/'submission.tar',d/'restored')
            self.assertEqual((d/'restored/encoder.py').read_text(),'example')
            self.assertFalse((d/'submission.tar').exists())
    def test_symlink_input_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            d=Path(d);source=d/'source';source.mkdir();(source/'bad').symlink_to('/etc/passwd')
            with self.assertRaises(ValueError):pack(source,d/'archive')
    def test_path_traversal_and_symlink_archives_rejected(self):
        for name,kind in [('../escape',tarfile.REGTYPE),('/absolute',tarfile.REGTYPE),('bad',tarfile.SYMTYPE)]:
            with tempfile.TemporaryDirectory() as d:
                d=Path(d)
                with tarfile.open(d/'archive','w') as tf:
                    info=tarfile.TarInfo(name);info.type=kind;info.linkname='/etc/passwd';info.size=0;tf.addfile(info,io.BytesIO())
                with self.assertRaises(ValueError):restore(d/'archive',d/'restored')
    def test_duplicate_members_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            d=Path(d)
            with tarfile.open(d/'archive','w') as tf:
                for _ in range(2):tf.addfile(tarfile.TarInfo('encoder.py'),io.BytesIO())
            with self.assertRaises(ValueError):restore(d/'archive',d/'restored')

if __name__=='__main__':unittest.main()
