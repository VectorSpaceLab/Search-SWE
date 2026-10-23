"""Real file-reference accounting in a disposable verifier; no GPU needed."""
import ctypes
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import grade
import storage_accounting as storage

CHILD = r'''
import ctypes,json,os,sys
from pathlib import Path
root=Path(sys.argv[1]);mode=sys.argv[2];size=2<<20
if mode=='tmpfile':
 fd=os.open(root,os.O_RDWR|os.O_TMPFILE,0o600)
else:
 fd=os.open(root/'cache',os.O_RDWR|os.O_CREAT|os.O_EXCL,0o600)
os.posix_fallocate(fd,0,size)
if mode in ('unlinked','mapped','hidden'):
 os.unlink(root/'cache')
if mode=='mapped':
 c=ctypes.CDLL(None,use_errno=True)
 c.mmap.argtypes=[ctypes.c_void_p,ctypes.c_size_t,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_long]
 c.mmap.restype=ctypes.c_void_p
 address=c.mmap(None,size,3,1,fd,0)
 assert address!=ctypes.c_void_p(-1).value
 os.close(fd)
if mode=='duplicate':
 duplicate=os.dup(fd);os.link(root/'cache',root/'hardlink')
if mode=='hidden':
 assert ctypes.CDLL(None).prctl(4,0,0,0,0)==0
print(json.dumps({'ready':True,'bytes':size}),flush=True)
sys.stdin.read()
'''


@unittest.skipUnless(Path('/.dockerenv').exists() and os.getuid()==0,
                     'requires disposable root verifier container')
class FileReferenceTests(unittest.TestCase):
    def setUp(self):
        storage.require_inspection_capabilities()
        # tmpfs supports O_TMPFILE even when the Docker overlay filesystem does not.
        self.temporary=tempfile.TemporaryDirectory(prefix='storage-fixture-', dir='/dev/shm')
        self.root=Path(self.temporary.name)
        self.root.chmod(0o755)
        self.index=self.root/'index';self.index.mkdir(mode=0o700)
        os.chown(self.index,10001,10001)
        self.process=None

    def tearDown(self):
        if self.process:
            self.process.kill();self.process.wait(timeout=5)
            self.process.stdin.close();self.process.stdout.close()
        grade.kill_new_processes({})
        self.temporary.cleanup()

    def start(self,mode):
        self.process=subprocess.Popen(['/usr/bin/setpriv','--reuid=10001','--regid=10001',
            '--clear-groups','--no-new-privs','--inh-caps=-all','--ambient-caps=-all',
            '--bounding-set=-all',sys.executable,'-c',CHILD,str(self.index),mode],
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
        self.assertTrue(json.loads(self.process.stdout.readline())['ready'])

    def test_named_file_and_duplicate_references_count_once(self):
        self.start('duplicate')
        self.assertEqual(storage.total_bytes([self.index],{}),2<<20)
        fixed=storage.inventory([self.index])
        self.assertEqual(storage.total_bytes([self.index],fixed),2<<20)

    def test_unlinked_open_file_still_counts(self):
        self.start('unlinked')
        self.assertEqual(storage.inventory([self.index]),{})
        self.assertEqual(storage.total_bytes([self.index],{}),2<<20)

    def test_anonymous_temporary_file_counts(self):
        self.start('tmpfile')
        self.assertEqual(storage.inventory([self.index]),{})
        self.assertEqual(storage.total_bytes([self.index],{}),2<<20)

    def test_mapping_survives_unlink_and_all_descriptor_closures(self):
        self.start('mapped')
        self.assertEqual(storage.inventory([self.index]),{})
        references=[os.readlink(p) for p in Path(f'/proc/{self.process.pid}/fd').iterdir()]
        self.assertFalse(any('cache' in value for value in references))
        self.assertEqual(storage.total_bytes([self.index],{}),2<<20)

    def test_nondumpable_process_cannot_hide_its_files(self):
        self.start('hidden')
        self.assertEqual(storage.total_bytes([self.index],{}),2<<20)

    def test_stopped_preparation_service_is_charged_during_later_command(self):
        self.start('unlinked')
        self.process.send_signal(signal.SIGSTOP)
        result=grade.run_command([sys.executable,'-c','print("normal query")'],
            cwd=self.root,index=self.index,timeout=5,log=self.root/'query.log',
            storage_roots=[self.index],fixed_files={},budget=1<<20)
        self.assertTrue(result['resource_violation'])
        self.assertGreaterEqual(result['peak_observed_storage_bytes'],2<<20)

    def test_visible_cache_and_zero_candidate_capabilities_are_legal(self):
        command='from pathlib import Path; print(next(s for s in Path("/proc/self/status").read_text().splitlines() if s.startswith("CapEff:")))'
        self.start('named')
        result=grade.run_command([sys.executable,'-c',command],cwd=self.root,index=self.index,
            timeout=5,log=self.root/'query.log',storage_roots=[self.index],fixed_files={},budget=4<<20)
        self.assertFalse(result['resource_violation'])
        self.assertEqual(result['returncode'],0)
        self.assertIn('0000000000000000',(self.root/'query.log').read_text())

    def test_completed_command_does_not_pay_for_slow_storage_inspection(self):
        def slow_inspection(*args, **kwargs):
            time.sleep(.3)
            return 0

        started=time.monotonic()
        with patch.object(grade,'total_bytes',side_effect=slow_inspection):
            result=grade.run_command([sys.executable,'-c','pass'],cwd=self.root,index=self.index,
                timeout=5,log=self.root/'query.log',storage_roots=[self.index],fixed_files={},budget=4<<20)
        self.assertEqual(result['returncode'],0)
        self.assertLess(result['elapsed_sec'],.3)
        self.assertGreater(time.monotonic()-started,.5)


class InspectionFailureTests(unittest.TestCase):
    def test_missing_capabilities_are_rejected(self):
        with patch.object(Path,'read_text',return_value='CapEff:\t0000000000000000\n'):
            with self.assertRaises(storage.StorageInspectionError):
                storage.require_inspection_capabilities()

    def test_permission_denied_is_not_silently_ignored(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);process=root/'123';process.mkdir()
            with patch.object(storage,'process_identity',side_effect=PermissionError):
                with self.assertRaises(storage.StorageInspectionError):
                    storage.total_bytes([],{},proc=root)

    def test_time_limit_fails_closed(self):
        with self.assertRaises(storage.StorageInspectionError):
            storage.total_bytes([Path('/tmp')],{},timeout=-1)


if __name__=='__main__':
    unittest.main()
