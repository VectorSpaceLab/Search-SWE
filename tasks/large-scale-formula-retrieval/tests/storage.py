"""A bounded ext4 image supplies real ENOSPC instead of an ignored Docker option."""
import os
import json
from pathlib import Path
import shutil
import stat

LIMIT = 64 << 30
LOG_RESERVE = 512 << 20
SERVING_LIMIT = 40 << 20
ARTIFACT_LIMIT = 34 << 20


def require_mount_permissions(root):
    for line in Path('/proc/self/mountinfo').read_text().splitlines():
        left, right = line.split(' - ', 1)
        fields, super_fields = left.split(), right.split()
        if fields[4] == str(root):
            options = set((fields[5] + ',' + super_fields[2]).split(','))
            if 'default_permissions' in options:
                return
    raise RuntimeError('Prepared FUSE mount must enforce default_permissions')


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
        require_mount_permissions(Path('/work'))
        marker = Path('/work/.storage.json')
        config = json.loads(marker.read_text())
        self.size = config['image_capacity_bytes']
        fixed = file_bytes('/task/data/public')
        if config['probe'] or config['public_bytes'] != fixed:
            raise RuntimeError('Storage preparation does not match current public inputs')
        if self.size != (LIMIT - fixed - LOG_RESERVE - SERVING_LIMIT) // 4096 * 4096:
            raise RuntimeError('Invalid prepared storage capacity')
        if config.get('prepared_artifact_limit_bytes') != ARTIFACT_LIMIT:
            raise RuntimeError('Invalid prepared artifact capacity')
        if config.get('serving_capacity_bytes') != SERVING_LIMIT:
            raise RuntimeError('Missing compact serving capacity')
        if os.stat('/work').st_dev == os.stat('/').st_dev:
            raise RuntimeError('Missing separate bounded work filesystem')
        fs = os.statvfs('/work')
        if fs.f_blocks * fs.f_frsize > self.size:
            raise RuntimeError('Mounted filesystem exceeds its prepared capacity')
        if any(p.name not in ['lost+found', '.storage.json'] for p in Path('/work').iterdir()):
            raise RuntimeError('Verifier requires unused run-specific storage')
        self.reserve = Path('/work/.submission-reserve')
        # Keep submitted files within the same 64 GiB accounting envelope even
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


def prepare_serving_volume():
    """Copy only the completed index into a physically bounded serving volume.

    Build workers have exited before this runs. Reject links and special files
    before privileged copying, then hide every original build/scratch artifact.
    """
    root = Path('/serve')
    require_mount_permissions(root)
    config = json.loads((root / '.storage.json').read_text())
    if (config.get('probe') or config.get('serving_capacity_bytes') != SERVING_LIMIT
            or config.get('prepared_artifact_limit_bytes') != ARTIFACT_LIMIT):
        raise RuntimeError('Invalid compact serving volume marker')
    if os.stat(root).st_dev in {os.stat('/').st_dev, os.stat('/work').st_dev}:
        raise RuntimeError('Serving requires its independent bounded filesystem')
    fs = os.statvfs(root)
    if fs.f_blocks * fs.f_frsize > SERVING_LIMIT:
        raise RuntimeError('Serving filesystem exceeds 40 MiB')
    if any(p.name not in ['lost+found', '.storage.json'] for p in root.iterdir()):
        raise RuntimeError('Serving requires unused run-specific storage')
    source = Path('/work/index')
    if any(not (stat.S_ISREG(p.lstat().st_mode) or stat.S_ISDIR(p.lstat().st_mode))
           for p in [source, *source.rglob('*')]):
        raise ValueError('Index must contain regular files and directories only')
    required = file_bytes('/app') + file_bytes(source)
    if required > ARTIFACT_LIMIT:
        raise ValueError('prepared artifact limit (34 MiB submission/models and index)')
    try:
        with (root / '.submission-reserve').open('xb') as stream:
            os.posix_fallocate(stream.fileno(), 0, max(4096, file_bytes('/app')))
        (root / '.submission-reserve').chmod(0o600)
        copied = {}
        def copy_index_file(src, dst):
            info = os.stat(src, follow_symlinks=False)
            key = (info.st_dev, info.st_ino)
            if key in copied:
                os.link(copied[key], dst)
            else:
                shutil.copy2(src, dst, follow_symlinks=False)
                copied[key] = dst
            return dst
        shutil.copytree(source, root / 'index', copy_function=copy_index_file)
        for p in [root / 'index', *(root / 'index').rglob('*')]:
            os.chown(p, 0, 10001)
            p.chmod(0o550 if p.is_dir() or p.stat().st_mode & 0o111 else 0o440)
        (root / 'runtime').mkdir(mode=0o700)
        os.chown(root / 'runtime', 10001, 10001)
    except OSError as exc:
        if exc.errno == 28:
            raise ValueError('serving footprint limit (filesystem full)') from exc
        raise
    os.chmod('/work', 0o700)
    return {'capacity_bytes': SERVING_LIMIT, 'artifact_limit_bytes': ARTIFACT_LIMIT,
            'submission_and_index_bytes': required,
            'free_bytes_before_queries': os.statvfs(root).f_bavail * os.statvfs(root).f_frsize}
