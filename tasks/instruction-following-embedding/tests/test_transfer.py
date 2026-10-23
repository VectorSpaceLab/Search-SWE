import io
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'environment/runtime'))
from submission_transfer import pack,restore,freeze_agent_processes

class TransferTests(unittest.TestCase):
    def test_freeze_refuses_a_host_runtime(self):
        with patch('submission_transfer.__file__', '/author/runtime/submission_transfer.py'):
            with self.assertRaisesRegex(RuntimeError, 'private task container'):
                freeze_agent_processes()

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
