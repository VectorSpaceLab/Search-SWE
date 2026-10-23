import importlib.util
import io
from pathlib import Path
import tarfile
import tempfile
import unittest

path = Path(__file__).resolve().parents[1] / "environment/runtime/transfer.py"
if not path.is_file():
    path = Path("/task/runtime/transfer.py")
spec = importlib.util.spec_from_file_location("molecular_transfer", path)
transfer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(transfer)


class TransferTests(unittest.TestCase):
    def test_roundtrip_and_reject_links(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            original = root / "original"
            original.mkdir()
            (original / "retriever.py").write_text("x = 1\n")
            transfer.pack(original, root / "submission.tar")
            transfer.restore(root / "submission.tar", root / "restored")
            self.assertEqual((root / "restored/retriever.py").read_text(), "x = 1\n")
            self.assertFalse((root / "submission.tar").exists())
            (original / "bad").symlink_to("/etc/passwd")
            with self.assertRaises(ValueError):
                transfer.pack(original, root / "submission.tar")

    def test_malicious_archive(self):
        for name, member_type in (("../outside", tarfile.REGTYPE), ("/outside", tarfile.REGTYPE),
                                  ("linked", tarfile.SYMTYPE), ("hard", tarfile.LNKTYPE)):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                with tarfile.open(root / "bad.tar", "w") as stream:
                    member = tarfile.TarInfo(name)
                    member.type = member_type
                    member.linkname = "/etc/passwd"
                    stream.addfile(member, io.BytesIO())
                with self.assertRaises(ValueError):
                    transfer.restore(root / "bad.tar", root / "destination")


if __name__ == "__main__":
    unittest.main()
