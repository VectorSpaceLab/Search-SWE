"""Logical-size regressions for retained descriptors and actual mmap-only files."""
import ctypes
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent / 'runtime'))
from storage import StorageBudget, logical_bytes


class StorageTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.libc = ctypes.CDLL(None, use_errno=True)
        self.libc.mmap.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int,
                                  ctypes.c_int, ctypes.c_int, ctypes.c_longlong]
        self.libc.mmap.restype = ctypes.c_void_p
        self.libc.munmap.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
        self.mappings = []
        self.addCleanup(self.unmap)

    def unmap(self):
        while self.mappings:
            self.assertEqual(self.libc.munmap(self.mappings.pop(), 4096), 0)

    def mapped(self, size, count=1):
        path = self.root / 'cache'
        descriptor = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            os.ftruncate(descriptor, size)
            for _ in range(count):
                address = self.libc.mmap(None, 4096, 3, 1, descriptor, 0)
                self.assertNotEqual(address, ctypes.c_void_p(-1).value, ctypes.get_errno())
                self.mappings.append(address)
        finally:
            os.close(descriptor)
        return path

    def usage(self, **kwargs):
        return logical_bytes([self.root], include_retained=True, **kwargs)

    def test_open_unlinked_files_keep_their_full_logical_size(self):
        path = self.root / 'cache'
        with path.open('w+b') as handle:
            handle.truncate(12 * 1024**2)
            path.unlink()
            self.assertEqual(self.usage(), 12 * 1024**2)
            with self.assertRaisesRegex(RuntimeError, 'storage exceeded'):
                StorageBudget((), [self.root], limit=10 * 1024**2).check(force=True)
        self.assertEqual(self.usage(), 0)

    def test_partial_mmap_retains_full_file_without_any_descriptor(self):
        size = 12 * 1024**2
        self.mapped(size).unlink()
        # Only 4 KiB is mapped. A range-size estimate would miss this violation.
        self.assertEqual(self.usage(), size)
        with self.assertRaisesRegex(RuntimeError, 'storage exceeded'):
            StorageBudget((), [self.root], limit=10 * 1024**2).check(force=True)
        self.unmap()
        self.assertEqual(self.usage(), 0)

    def test_named_file_descriptors_and_mappings_are_not_counted_again(self):
        size = 2 * 1024**2
        path = self.mapped(size, count=2)
        with path.open('rb') as first, path.open('rb') as second:
            self.assertEqual(self.usage(), size)
            path.unlink()
            self.assertEqual(self.usage(), size)
            self.assertEqual(first.read(1), second.read(1))
        self.assertEqual(self.usage(), size)
        self.unmap()
        self.assertEqual(self.usage(), 0)

    def test_excluded_framework_directory_stays_excluded_when_mapped(self):
        path = self.mapped(2 * 1024**2)
        self.assertEqual(self.usage(excluded={str(self.root)}), 0)
        path.unlink()
        self.assertEqual(self.usage(excluded={str(self.root)}), 0)

    def test_mapping_disappearing_during_sampling_is_tolerated(self):
        self.mapped(2 * 1024**2).unlink()
        original = Path.stat
        released = False

        def release(path, *args, **kwargs):
            nonlocal released
            if 'map_files' in path.parts and not released:
                self.unmap()
                released = True
            return original(path, *args, **kwargs)

        with patch.object(Path, 'stat', release):
            self.assertEqual(self.usage(), 0)
        self.assertTrue(released)

    def test_uninspectable_mapping_fails_closed(self):
        self.mapped(2 * 1024**2).unlink()
        original = Path.stat

        def deny(path, *args, **kwargs):
            if 'map_files' in path.parts:
                raise PermissionError(str(path))
            return original(path, *args, **kwargs)

        identity = os.getresuid(), os.getresgid()
        with patch.object(Path, 'stat', deny), self.assertRaisesRegex(RuntimeError, 'Cannot inspect submission'):
            self.usage()
        self.assertEqual((os.getresuid(), os.getresgid()), identity)

    def test_unreadable_directory_fails_closed(self):
        with patch('storage.os.walk', side_effect=lambda *args, **kwargs: kwargs['onerror'](PermissionError('denied'))):
            with self.assertRaises(PermissionError):
                self.usage()


if __name__ == '__main__':
    unittest.main()
