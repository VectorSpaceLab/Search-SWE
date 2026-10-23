"""A bounded ext4 image supplies real ENOSPC instead of an ignored Docker option."""
import os
import json
from pathlib import Path
import subprocess
import time

LIMIT = 100 << 30
LOG_RESERVE = 512 << 20


def file_bytes(root):
    total = 0
    seen = set()
    for p in Path(root).rglob('*'):
        if p.is_file() and not p.is_symlink():
            s = p.stat()
            identity = (s.st_dev, s.st_ino)
            if identity not in seen:
                seen.add(identity)
                total += max(s.st_size, s.st_blocks * 512)
    return total


class QuotaVolume:
    def __init__(self, size, mount='/work', image='/quota/work.img'):
        self.mount, self.image = Path(mount), Path(image)
        self.process = None
        self.log = None
        self.size = size

    def __enter__(self):
        self.image.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.image.parent.chmod(0o700)
        self.mount.mkdir(parents=True, exist_ok=True)
        if self.image.exists() or any(self.mount.iterdir()):
            raise RuntimeError('Quota setup requires an empty mount and a fresh private image')
        if self.size < 64 << 20:
            raise RuntimeError('Insufficient storage after fixed inputs and logs')
        with self.image.open('xb') as f:
            f.truncate(self.size)
        self.image.chmod(0o600)
        # Nonzero reserved percentage: fuse2fs substitutes 10% when reserved blocks=0.
        subprocess.run(['mkfs.ext4', '-q', '-F', '-b', '4096', '-m', '0.01',
                        '-O', '^has_journal', str(self.image)], check=True, timeout=120)
        self.log = (self.image.parent / 'fuse.log').open('wb')
        self.process = subprocess.Popen(['fuse2fs', '-f', '-o', 'rw,allow_other',
                                         str(self.image), str(self.mount)],
                                        stdout=self.log, stderr=subprocess.STDOUT)
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise RuntimeError('Quota filesystem failed to mount; inspect /quota/fuse.log')
            if os.path.ismount(self.mount):
                os.chmod(self.mount, 0o755)
                return self
            time.sleep(.05)
        self.__exit__(None, None, None)
        raise RuntimeError('Quota filesystem mount timed out')

    def __exit__(self, *unused):
        if os.path.ismount(self.mount):
            subprocess.run(['umount', str(self.mount)], check=True, timeout=15)
        if self.process is not None:
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        if self.log:
            self.log.close()
        if self.image.exists():
            self.image.unlink()


class PreparedVolume:
    """Use the dedicated bounded filesystem prepared before Harbor startup."""
    def __enter__(self):
        marker = Path('/work/.storage.json')
        config = json.loads(marker.read_text())
        self.size = config['image_capacity_bytes']
        fixed = file_bytes('/task/data/public')
        if config['probe'] or config['public_bytes'] != fixed:
            raise RuntimeError('Storage preparation does not match current public inputs')
        if self.size != (LIMIT - fixed - LOG_RESERVE) // 4096 * 4096:
            raise RuntimeError('Invalid prepared storage capacity')
        if os.stat('/work').st_dev == os.stat('/').st_dev:
            raise RuntimeError('Missing separate bounded work filesystem')
        fs = os.statvfs('/work')
        if fs.f_blocks * fs.f_frsize > self.size:
            raise RuntimeError('Mounted filesystem exceeds its prepared capacity')
        if any(p.name not in ['lost+found', '.storage.json'] for p in Path('/work').iterdir()):
            raise RuntimeError('Verifier requires unused run-specific storage')
        self.reserve = Path('/work/.submission-reserve')
        # Keep submitted files within the same 100 GiB accounting envelope even
        # though Harbor transfers them to /app after host storage is prepared.
        with self.reserve.open('xb') as stream:
            stream.seek(0)
            os.posix_fallocate(stream.fileno(), 0, max(4096, file_bytes('/app')))
        self.reserve.chmod(0o600)
        return self

    def __exit__(self, *unused):
        self.reserve.unlink(missing_ok=True)


def evaluation_volume():
    return PreparedVolume()
