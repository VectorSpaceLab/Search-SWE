"""Container-only compact filesystem checks with task-prepared /work and /serve."""
import errno
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest

from storage import prepare_serving_volume, SERVING_LIMIT, ARTIFACT_LIMIT


@unittest.skipUnless(Path('/.dockerenv').exists() and os.getuid() == 0
                     and Path('/serve/.storage.json').exists(), 'requires disposable prepared verifier')
class ServingStorageTests(unittest.TestCase):
    def setUp(self):
        Path('/work').chmod(0o755)
        for root in [Path('/work/index'), Path('/app/submission')]:
            if root.exists():
                shutil.rmtree(root)
            root.mkdir(parents=True)
        Path('/app/submission/readme').write_text('fixture')

    def tearDown(self):
        for p in Path('/serve').iterdir():
            if p.name in ['lost+found', '.storage.json']:
                continue
            if p.is_dir():
                shutil.rmtree(p)
            else:
                p.unlink()
        Path('/work').chmod(0o755)

    def test_index_readonly_and_build_scratch_hidden(self):
        Path('/work/index/index.bin').write_text('prepared')
        Path('/work/private-scratch').write_text('must be inaccessible')
        info = prepare_serving_volume()
        self.assertEqual(info['capacity_bytes'], SERVING_LIMIT)
        code = '''from pathlib import Path
assert Path('/serve/index/index.bin').read_text() == 'prepared'
for p in ['/work/private-scratch','/serve/.submission-reserve']:
 try: Path(p).read_bytes()
 except PermissionError: pass
 else: raise AssertionError('private file readable: '+p)
for p in ['/serve/index/index.bin','/serve/.submission-reserve']:
 try:
  with open(p,'w') as f: f.write('bypass')
 except PermissionError: pass
 else: raise AssertionError(p)
Path('/serve/runtime/cache').write_text('allowed')
'''
        p = subprocess.run([sys.executable, '-c', code], user=10001, group=10001,
                           extra_groups=[], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)

    def test_symlink_cannot_copy_private_labels(self):
        Path('/work/index/leak').symlink_to('/tests/data/qrels.tsv')
        with self.assertRaisesRegex(ValueError, 'regular files'):
            prepare_serving_volume()
        self.assertFalse(Path('/serve/index').exists())

    def test_oversized_index_rejected(self):
        with Path('/work/index/oversized').open('wb') as f:
            f.truncate(ARTIFACT_LIMIT + 1)
        with self.assertRaisesRegex(ValueError, 'prepared artifact limit'):
            prepare_serving_volume()

    def test_exact_prepared_artifact_limit_fits_with_runtime_headroom(self):
        with Path('/work/index/boundary').open('wb') as f:
            os.posix_fallocate(f.fileno(), 0, ARTIFACT_LIMIT - 4096)
        info = prepare_serving_volume()
        self.assertEqual(info['artifact_limit_bytes'], ARTIFACT_LIMIT)
        self.assertEqual(info['submission_and_index_bytes'], ARTIFACT_LIMIT)
        self.assertGreater(info['free_bytes_before_queries'], 1 << 20)

    def test_hardlinks_remain_shared(self):
        Path('/work/index/first').write_text('one allocation')
        os.link('/work/index/first', '/work/index/second')
        prepare_serving_volume()
        self.assertEqual(Path('/serve/index/first').stat().st_ino,
                         Path('/serve/index/second').stat().st_ino)

    def test_real_enospc_for_serving_cache(self):
        Path('/work/index/index.bin').write_text('prepared')
        prepare_serving_volume()
        available = os.statvfs('/serve/runtime').f_bavail * os.statvfs('/serve/runtime').f_frsize
        code = '''import errno,json
total=0
try:
 with open('/serve/runtime/cache','wb',buffering=0) as f:
  while True: total += f.write(b'x'*(1<<20))
except OSError as e:
 assert e.errno == errno.ENOSPC
print(json.dumps({'bytes':total}))
'''
        p = subprocess.run([sys.executable, '-c', code], user=10001, group=10001,
                           extra_groups=[], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        written = json.loads(p.stdout)['bytes']
        self.assertGreater(written, available - (2 << 20))
        self.assertLess(written, SERVING_LIMIT)
