"""Storage and executable-submission regressions in a disposable CPU container."""

import sys
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(TASK_ROOT / "tests"))

import os
import selectors
import shutil
import subprocess
import tempfile
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch

IN_CONTAINER = Path('/task/runtime').is_dir() and Path('/opt/conda/bin/python').is_file()
if IN_CONTAINER:
    sys.path.insert(0, '/task/runtime')
    from evaluate import Resources, ResourceViolation, snapshot, writable_bytes
    from isolation import UID, cleanup, isolate
    from submission_transfer import pack, restore


@unittest.skipUnless(IN_CONTAINER, 'disposable container required')
class RuntimeCPUTest(unittest.TestCase):
    def setUp(self):
        cleanup()
        for path in ['/task/models', '/task/public', '/app/submission']:
            Path(path).mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir='/app')
        self.work = Path(self.temp.name)
        os.chown(self.work, UID, UID)

    def tearDown(self):
        cleanup()
        self.temp.cleanup()

    def meter(self):
        meter = Resources.__new__(Resources)
        meter.gpu = None
        meter.fixed = meter.peak_gpu = meter.peak_storage = meter.last_disk = 0
        return meter

    def test_gpu_selection_does_not_require_a_model_or_memory_capacity(self):
        with patch('evaluate.pynvml.nvmlInit'), \
                patch('evaluate.pynvml.nvmlDeviceGetCount', return_value=1), \
                patch('evaluate.pynvml.nvmlDeviceGetHandleByIndex', return_value='assigned'), \
                patch('evaluate.pynvml.nvmlDeviceGetName', side_effect=AssertionError('model restriction')), \
                patch('evaluate.pynvml.nvmlDeviceGetMemoryInfo', side_effect=AssertionError('capacity restriction')):
            self.assertEqual(Resources().gpu, 'assigned')

    def test_gpu_selection_requires_exactly_one_device(self):
        for count in (0, 2):
            with self.subTest(count=count), patch('evaluate.pynvml.nvmlInit'), \
                    patch('evaluate.pynvml.nvmlDeviceGetCount', return_value=count), \
                    self.assertRaisesRegex(ResourceViolation, 'Exactly one mapped GPU'):
                Resources()

    def check(self, meter):
        meter.last_disk = 0
        with patch('evaluate.pynvml.nvmlDeviceGetMemoryInfo', return_value=SimpleNamespace(used=0)):
            meter.check()

    def child(self, code):
        program = ("import sys\nfrom pathlib import Path\nsys.path.insert(0, '/task/runtime')\n"
                   "from isolation import isolate\nisolate(Path(sys.argv[1]))\n" + code)
        child = subprocess.Popen(['/opt/conda/bin/python', '-c', program, str(self.work)],
                                 stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 text=True)
        self.addCleanup(self.stop_child, child)
        with selectors.DefaultSelector() as ready:
            ready.register(child.stdout, selectors.EVENT_READ)
            self.assertTrue(ready.select(10), 'child did not become ready')
        self.assertEqual(child.stdout.readline().strip(), 'ready')
        return child

    @staticmethod
    def stop_child(child):
        if child.poll() is None:
            child.kill()
        child.communicate(timeout=5)

    def test_archive_restore_snapshot_preserves_executable_helper(self):
        source = self.work / 'source'
        source.mkdir()
        (source / 'encoder.py').write_text('# fixture\n')
        helper = source / 'helper.sh'
        helper.write_text('#!/bin/sh\nprintf helper-ok\n')
        helper.chmod(0o755)
        submission = Path('/app/submission')
        shutil.rmtree(submission)
        archive = self.work / 'submission.tar'
        pack(source, archive)
        restore(archive, submission)
        snapshot()
        self.assertEqual((submission / 'helper.sh').stat().st_mode & 0o777, 0o555)
        self.assertEqual((submission / 'encoder.py').stat().st_mode & 0o777, 0o444)
        result = subprocess.run(['/app/submission/helper.sh'], capture_output=True, text=True,
                                preexec_fn=lambda: isolate(self.work), timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, 'helper-ok')

    def test_normal_temporary_file_churn_does_not_fail_accounting(self):
        stop = threading.Event()
        def churn():
            while not stop.is_set():
                for index in range(12):
                    path = self.work / str(index)
                    path.write_bytes(b'ordinary temporary file')
                    path.unlink()
        thread = threading.Thread(target=churn)
        thread.start()
        try:
            meter = self.meter()
            for _ in range(100):
                self.check(meter)
        finally:
            stop.set()
            thread.join()

    def test_file_removed_during_stat_is_ignored_but_permission_failure_is_not(self):
        target = self.work / 'temporary'
        target.write_bytes(b'data')
        lstat = Path.lstat
        def disappear(path):
            if path == target:
                path.unlink()
            return lstat(path)
        with patch.object(Path, 'lstat', disappear):
            writable_bytes()
        target.write_bytes(b'data')
        def denied(path):
            if path == target:
                raise PermissionError(str(path))
            return lstat(path)
        with patch.object(Path, 'lstat', denied), self.assertRaises(ResourceViolation):
            writable_bytes()

    def test_open_unlinked_sparse_files_still_exceed_storage_limit(self):
        handles = []
        try:
            for index in range(2):
                path = self.work / str(index)
                handle = path.open('wb')
                handle.truncate(60 << 30)
                handles.append(handle)
            with self.assertRaises(ResourceViolation):
                self.check(self.meter())
            for index in range(2):
                (self.work / str(index)).unlink()
            with self.assertRaises(ResourceViolation):
                self.check(self.meter())
        finally:
            for handle in handles:
                handle.close()

    def test_named_links_count_per_path_but_duplicate_descriptors_do_not(self):
        baseline = writable_bytes()
        path = self.work / 'file'
        path.write_bytes(b'x' * 4096)
        with path.open('rb') as first, path.open('rb') as second:
            self.assertEqual(writable_bytes() - baseline, 4096)
            os.link(path, self.work / 'alias')
            self.assertEqual(writable_bytes() - baseline, 8192)
            path.unlink()
            (self.work / 'alias').unlink()
            self.assertEqual(writable_bytes() - baseline, 4096)
            self.assertEqual(first.read(1), second.read(1))

    def test_unprivileged_child_deleted_files_are_counted(self):
        self.child("""
import os
handles = []
for name in ['first', 'second']:
    handle = open(name, 'wb')
    handle.truncate(60 << 30)
    os.unlink(name)
    handles.append(handle)
print('ready', flush=True)
sys.stdin.readline()
""")
        identity = os.getresuid(), os.getresgid()
        with self.assertRaises(ResourceViolation):
            self.check(self.meter())
        self.assertEqual((os.getresuid(), os.getresgid()), identity)

    def test_live_child_cannot_hide_open_files(self):
        self.child("""
import ctypes
assert ctypes.CDLL(None).prctl(4, 0, 0, 0, 0) == 0
print('ready', flush=True)
sys.stdin.readline()
""")
        with self.assertRaisesRegex(ResourceViolation, 'inspect submission'):
            writable_bytes()

    def test_exiting_children_do_not_fail_accounting(self):
        child = self.child("""
import subprocess
print('ready', flush=True)
for _ in range(15):
    subprocess.run(['/opt/conda/bin/python', '-c', 'pass'], check=True)
""")
        while child.poll() is None:
            writable_bytes()
        self.assertEqual(child.returncode, 0, child.stderr.read())


if __name__ == '__main__':
    unittest.main()
