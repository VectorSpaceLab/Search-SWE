"""Real isolated-process storage checks; run only in a disposable container."""
import json
import os
from pathlib import Path
import selectors
import subprocess
import sys
import tempfile
import textwrap
import unittest
from unittest.mock import patch

sys.path.insert(0, '/task/runtime')


@unittest.skipUnless(os.environ.get('SEARCH_SWE_SANDBOX_TEST') == '1',
                     'Disposable verifier container required')
class StorageTests(unittest.TestCase):
    def setUp(self):
        import evaluate
        from isolation import UID, cleanup
        self.evaluate = evaluate
        cleanup()
        for root in ('/app/submission', '/task/models', '/task/corpus', '/task/data'):
            Path(root).mkdir(parents=True, exist_ok=True)
        directory = tempfile.TemporaryDirectory(prefix='retained-storage-', dir='/app')
        self.addCleanup(directory.cleanup)
        self.addCleanup(cleanup)
        self.work = Path(directory.name)
        os.chown(self.work, UID, UID)

    def meter(self):
        with patch.object(self.evaluate.pynvml, 'nvmlInit'), \
                patch.object(self.evaluate.pynvml, 'nvmlDeviceGetCount', return_value=1):
            return self.evaluate.Resources()

    def sample(self):
        meter = self.meter()
        meter.check()
        return meter.peak_disk

    def child(self, *, size=20 << 30, count=2, mapped=True, memfd=False, aliases=False,
              retired_leader=False):
        program = f'size={size}; count={count}; mapped={mapped}; memfd={memfd}; aliases={aliases}\n' + '''import ctypes,json,os,sys
from pathlib import Path
sys.path.insert(0, '/task/runtime')
from isolation import isolate
isolate(Path(sys.argv[1]))
status = dict(line.split(':', 1) for line in Path('/proc/self/status').read_text().splitlines() if ':' in line)
assert os.getuid() == 10001 and int(status['CapEff'], 16) == int(status['CapPrm'], 16) == 0
libc = ctypes.CDLL(None, use_errno=True)
libc.mmap.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_longlong]
libc.mmap.restype = ctypes.c_void_p
libc.munmap.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
libc.memfd_create.argtypes = [ctypes.c_char_p, ctypes.c_uint]
'''
        serve = '''names, descriptors, mappings = [], [], []
for number in range(count):
    name = 'retained-' + str(number)
    fd = libc.memfd_create(name.encode(), 0) if memfd else os.open(name, os.O_CREAT | os.O_RDWR, 0o600)
    assert fd >= 0, ctypes.get_errno()
    os.ftruncate(fd, size)
    descriptors.append(fd)
    if not memfd:
        names.append(name)
        if aliases:
            os.link(name, name + '-alias')
            names.append(name + '-alias')
    if mapped:
        # Two partial mappings and an FD refer to the same full backing file.
        for _ in range(2):
            address = libc.mmap(None, 4096, 3, 1, fd, 0)
            assert address != ctypes.c_void_p(-1).value, ctypes.get_errno()
            ctypes.memmove(address, b'canary00', 8)
            mappings.append(address)
print(json.dumps({'stage':'named', 'size':size*count, 'uid':os.getuid()}), flush=True)
for command in sys.stdin:
    command = command.strip()
    if command == 'unlink':
        for name in names:
            os.unlink(name)
        names.clear()
        if mapped:
            for fd in descriptors:
                os.close(fd)
            descriptors.clear()
            for entry in os.listdir('/proc/thread-self/fd'):
                try:
                    assert 'retained-' not in os.readlink('/proc/thread-self/fd/' + entry)
                except FileNotFoundError:
                    pass
    elif command == 'release':
        for address in mappings:
            assert libc.munmap(address, 4096) == 0
        mappings.clear()
        for fd in descriptors:
            os.close(fd)
        descriptors.clear()
    elif command == 'hide':
        assert libc.prctl(4, 0, 0, 0, 0) == 0
    elif command == 'exit':
        break
    assert all(ctypes.string_at(address, 8) == b'canary00' for address in mappings)
    print(json.dumps({'stage':command, 'descriptors':len(descriptors), 'mappings':len(mappings)}), flush=True)
'''
        if retired_leader:
            wait = '''import time
for _ in range(2000):
    if Path('/proc/self/stat').read_text().rsplit(') ', 1)[1].split()[0] == 'Z':
        break
    time.sleep(.001)
else:
    os._exit(3)
'''
            program += 'import threading\ndef serve():\n' + textwrap.indent(wait + serve, '    ')
            program += '''threading.Thread(target=threading.Event().wait).start()
threading.Thread(target=serve).start()
libc.pthread_exit.argtypes = [ctypes.c_void_p]
libc.pthread_exit(None)
'''
        else:
            program += serve
        child = subprocess.Popen([sys.executable, '-B', '-c', program, str(self.work)],
                                 stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.addCleanup(self.stop_child, child)
        self.message(child)
        return child

    @staticmethod
    def stop_child(child):
        if child.poll() is None:
            child.kill()
        child.communicate(timeout=5)

    def message(self, child):
        with selectors.DefaultSelector() as ready:
            ready.register(child.stdout, selectors.EVENT_READ)
            self.assertTrue(ready.select(10), 'isolated child did not respond')
        line = child.stdout.readline()
        if not line:
            self.fail(child.stderr.read())
        return json.loads(line)

    def command(self, child, command):
        child.stdin.write(command + '\n')
        child.stdin.flush()
        return self.message(child)

    def test_named_and_fd_only_40gib_files_are_rejected(self):
        child = self.child(mapped=False)
        for stage in ('named', 'unlinked'):
            with self.subTest(stage=stage):
                if stage == 'unlinked':
                    self.command(child, 'unlink')
                with self.assertRaisesRegex(self.evaluate.ResourceViolation, '32 GiB'):
                    self.sample()

    def test_partial_mmap_only_40gib_files_are_rejected(self):
        child = self.child()
        with self.assertRaisesRegex(self.evaluate.ResourceViolation, '32 GiB'):
            self.sample()
        state = self.command(child, 'unlink')
        self.assertEqual(state['descriptors'], 0)
        self.assertEqual(state['mappings'], 4)
        with self.assertRaisesRegex(self.evaluate.ResourceViolation, '32 GiB'):
            self.sample()

    def test_surviving_thread_retained_files_exceed_budget(self):
        for mapped in (False, True):
            with self.subTest(mapped=mapped):
                child = self.child(mapped=mapped, retired_leader=True)
                self.command(child, 'unlink')
                with self.assertRaisesRegex(self.evaluate.ResourceViolation, '32 GiB'):
                    self.sample()
                self.stop_child(child)

    def test_surviving_thread_references_deduplicate_and_release(self):
        for mapped in (False, True):
            with self.subTest(mapped=mapped):
                baseline = self.sample()
                child = self.child(size=2 << 20, count=1, mapped=mapped, retired_leader=True)
                self.command(child, 'unlink')
                self.assertEqual(self.sample() - baseline, 2 << 20)
                self.command(child, 'release')
                self.assertEqual(self.sample(), baseline)
                self.stop_child(child)

    def test_surviving_thread_cannot_disable_inspection(self):
        child = self.child(size=2 << 20, count=1, retired_leader=True)
        self.command(child, 'unlink')
        self.command(child, 'hide')
        with self.assertRaisesRegex(self.evaluate.ResourceViolation, 'inspect submission'):
            self.sample()

    def test_memfd_mappings_count_after_all_descriptors_close(self):
        child = self.child(memfd=True)
        self.command(child, 'unlink')
        with self.assertRaisesRegex(self.evaluate.ResourceViolation, '32 GiB'):
            self.sample()

    def test_under_budget_references_deduplicate_and_release(self):
        baseline = self.sample()
        child = self.child(size=2 << 20, count=1)
        self.assertEqual(self.sample() - baseline, 2 << 20)
        self.command(child, 'unlink')
        self.assertEqual(self.sample() - baseline, 2 << 20)
        self.command(child, 'release')
        self.assertEqual(self.sample(), baseline)

    def test_under_budget_fd_release_is_counted(self):
        baseline = self.sample()
        child = self.child(size=2 << 20, count=1, mapped=False)
        self.command(child, 'unlink')
        self.assertEqual(self.sample() - baseline, 2 << 20)
        self.command(child, 'release')
        self.assertEqual(self.sample(), baseline)

    def test_named_hardlink_accounting_is_preserved(self):
        baseline = self.sample()
        child = self.child(size=2 << 20, count=1, aliases=True)
        self.assertEqual(self.sample() - baseline, 4 << 20)
        self.command(child, 'unlink')
        self.assertEqual(self.sample() - baseline, 2 << 20)

    def test_uninspectable_live_worker_is_a_resource_violation(self):
        child = self.child(size=2 << 20, count=1)
        self.command(child, 'unlink')
        self.command(child, 'hide')
        with self.assertRaisesRegex(self.evaluate.ResourceViolation, 'inspect submission'):
            self.sample()

    def test_mapping_released_during_inspection_is_tolerated(self):
        baseline = self.sample()
        child = self.child(size=2 << 20, count=1)
        self.command(child, 'unlink')
        original = Path.stat
        released = False

        def release(path, *args, **kwargs):
            nonlocal released
            if 'map_files' in path.parts and not released:
                self.command(child, 'release')
                released = True
            return original(path, *args, **kwargs)

        with patch.object(Path, 'stat', release):
            self.assertEqual(self.sample(), baseline)
        self.assertTrue(released)

    def test_inspection_denial_fails_closed_and_restores_supervisor(self):
        child = self.child(size=2 << 20, count=1)
        self.command(child, 'unlink')
        original = Path.stat
        identity = os.getresuid(), os.getresgid()

        def denied(path, *args, **kwargs):
            if 'map_files' in path.parts:
                raise PermissionError(str(path))
            return original(path, *args, **kwargs)

        with patch.object(Path, 'stat', denied), self.assertRaisesRegex(self.evaluate.ResourceViolation, 'inspect submission'):
            self.sample()
        self.assertEqual((os.getresuid(), os.getresgid()), identity)

    def test_final_report_forces_storage_check(self):
        meter = self.meter()
        meter.check()
        child = self.child()
        self.command(child, 'unlink')
        import time
        meter.last_disk = time.monotonic()
        with self.assertRaisesRegex(self.evaluate.ResourceViolation, '32 GiB'):
            meter.report()


if __name__ == '__main__':
    unittest.main()
