"""Fixed-count timing summaries and immutable preparation artifacts."""
import math
import os
from pathlib import Path
import shutil
import stat
import statistics

TIMING_REPEATS = 5


def median_seconds(samples):
    if len(samples) != TIMING_REPEATS:
        raise ValueError("Exactly five timing samples are required")
    values = []
    for sample in samples:
        if sample is None:
            values.append(math.inf)
        elif type(sample) not in (int, float) or not math.isfinite(sample) or sample < 0:
            raise ValueError("Invalid timing sample")
        else:
            values.append(float(sample))
    value = statistics.median(values)
    return value if math.isfinite(value) else None


def reset_scratch(root, name, uid=10001):
    root = Path(root)
    scratch = root / name
    if scratch.is_symlink() or scratch.is_file():
        scratch.unlink()
    elif scratch.exists():
        shutil.rmtree(scratch)
    scratch.mkdir(mode=0o700)
    os.chown(scratch, uid, uid)
    return scratch


def freeze_prepared(root, scratch_name, uid=10001):
    """Retain prepared files while resetting mutable per-run scratch."""
    root = Path(root)
    scratch = reset_scratch(root, scratch_name, uid)
    for path in sorted(root.rglob("*"), reverse=True):
        if path == scratch or scratch in path.parents:
            continue
        info = path.lstat()
        if not (stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode)):
            raise ValueError("Prepared state must contain regular files and directories")
        os.chown(path, 0, 0)
        path.chmod(0o755 if stat.S_ISDIR(info.st_mode) or info.st_mode & 0o111 else 0o444)
    os.chown(root, 0, 0)
    root.chmod(0o755)
