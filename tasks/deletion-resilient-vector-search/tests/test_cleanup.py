"""Regression checks for delayed FUSE directory release."""
import errno
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from storage import remove_work_tree


class CleanupTests(unittest.TestCase):
    def test_transient_nonempty_directory_is_retried(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'work'
            path.mkdir()
            (path / 'payload').write_text('fixture')
            original = shutil.rmtree
            calls = []

            def delayed(target):
                calls.append(target)
                if len(calls) == 1:
                    raise OSError(errno.ENOTEMPTY, 'delayed FUSE release')
                original(target)

            with patch('storage.shutil.rmtree', side_effect=delayed):
                remove_work_tree(path)
            self.assertEqual(len(calls), 2)
            self.assertFalse(path.exists())

    def test_permanent_error_is_not_hidden(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            with patch('storage.shutil.rmtree', side_effect=PermissionError(errno.EACCES, 'denied')):
                with self.assertRaises(PermissionError):
                    remove_work_tree(path)

    def test_missing_tree_is_already_clean(self):
        with tempfile.TemporaryDirectory() as directory:
            remove_work_tree(Path(directory) / 'missing')

    def test_nonempty_error_expires_at_cleanup_deadline(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch('storage.shutil.rmtree', side_effect=OSError(errno.ENOTEMPTY, 'persistent')), \
                    patch('storage.time.monotonic', side_effect=[0, 3]):
                with self.assertRaises(OSError):
                    remove_work_tree(Path(directory))


if __name__ == '__main__':
    unittest.main()
