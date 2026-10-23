"""A bounded ext4 image supplies real ENOSPC instead of an ignored Docker option."""
import os
import json
from pathlib import Path

LIMIT = 32 << 30
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
        # Keep submitted files within the same 32 GiB accounting envelope even
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
