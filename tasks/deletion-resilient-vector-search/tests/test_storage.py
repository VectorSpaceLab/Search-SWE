"""Container-only ENOSPC regression on a small image using the real quota mechanism."""
import os
from pathlib import Path
import subprocess
import unittest

from storage import QuotaVolume


@unittest.skipUnless(Path('/.dockerenv').exists() and Path('/dev/fuse').exists(), 'requires disposable verifier with FUSE')
class QuotaTests(unittest.TestCase):
    def test_kernel_backed_capacity(self):
        with QuotaVolume(128 << 20, '/quota-test-mount', '/quota-test-private/work.img') as volume:
            os.chown(volume.mount, 10001, 10001)
            result = subprocess.run(['runuser', '-u', 'submission', '--', 'dd', 'if=/dev/zero',
                                     f'of={volume.mount}/over-limit', 'bs=1M', 'count=256', 'status=none'],
                                    capture_output=True, timeout=30)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(b'No space left on device', result.stderr)
            self.assertLessEqual((volume.mount / 'over-limit').stat().st_size, 128 << 20)
            hidden = subprocess.run(['runuser', '-u', 'submission', '--', 'test', '-r', str(volume.image)])
            self.assertNotEqual(hidden.returncode, 0)


if __name__ == '__main__':
    unittest.main()
