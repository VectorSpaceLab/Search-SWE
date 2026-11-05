"""Resource policy and machine-local preparation checks shared by both phases."""
import hashlib
import importlib
import json
import os
from pathlib import Path
import sys

CPU_COUNT = 16
TIMING_REPEATS = 5
EXACT_SCAN_FRACTION = 0.10
BUILD_SECONDS = 3600
INSERT_SECONDS = 60
LIMITS_PATH = Path('/task/platform/limits.json')


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def select_cpus():
    available = sorted(os.sched_getaffinity(0))
    if len(available) < CPU_COUNT:
        raise RuntimeError(f'At least {CPU_COUNT} available logical CPUs are required')
    return available[:CPU_COUNT]


def kernel_signature():
    import faiss
    import numpy as np
    wrapper = importlib.import_module(faiss.fvec_L2sqr.__module__)
    binary = getattr(wrapper, '_' + wrapper.__name__.rsplit('.', 1)[-1])
    rng = np.random.Generator(np.random.PCG64(260306660))
    vectors = rng.random((9, 3072), dtype=np.float32)
    probe = np.asarray([faiss.fvec_L2sqr(faiss.swig_ptr(vectors[0]),
                        faiss.swig_ptr(vectors[i]), dim)
                        for dim in (1536, 3072) for i in range(1, 9)], dtype='<f4')
    return {'faiss_version': faiss.__version__,
            'compile_options': faiss.get_compile_options().strip(),
            'binary_sha256': digest(binary.__file__),
            'probe_sha256': hashlib.sha256(probe.tobytes()).hexdigest()}


def platform_fingerprint():
    # CPU numbers are discovered locally, never prescribed by the task. Including
    # them in this opaque cache key detects allocation changes after calibration.
    cpus = select_cpus()
    fields = {'processor', 'model name', 'cpu family', 'model', 'stepping',
              'microcode', 'physical id', 'core id', 'flags'}
    processors = []
    for block in Path('/proc/cpuinfo').read_text().split('\n\n'):
        record = {key.strip(): value.strip() for line in block.splitlines()
                  if ':' in line for key, value in [line.split(':', 1)]
                  if key.strip() in fields}
        if record.get('processor', '').isdigit() and int(record['processor']) in cpus:
            processors.append(record)
    controls = {}
    for name in ('cpu.max', 'memory.max'):
        path = Path('/sys/fs/cgroup') / name
        controls[name] = path.read_text().strip() if path.exists() else None
    # Hardware identity is stable across a reboot. A boot ID would unnecessarily
    # invalidate hours of reference measurements on an otherwise unchanged host.
    identity = Path('/sys/class/dmi/id/product_uuid')
    value = {'cpus': cpus, 'processors': processors, 'controls': controls,
             'machine': os.uname().machine, 'kernel': os.uname().release,
             'hardware': identity.read_text().strip() if identity.exists() else None}
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def load_runtime_limits(path=None):
    path = Path(path) if path is not None else LIMITS_PATH
    try:
        value = json.loads(path.read_text())
    except (OSError, ValueError) as error:
        raise RuntimeError('Platform preparation is missing or invalid; start this task through search-swe run or scripts/evaluation/run_task.py') from error
    if value.get('schema_version') != 2 or value.get('timing_repeats') != TIMING_REPEATS:
        raise RuntimeError('Formal verification must use five independent timing replays')
    if value.get('platform_fingerprint') != platform_fingerprint():
        raise RuntimeError('Machine or CPU allocation changed; restart through the evaluation launcher to prepare matching limits')
    if value.get('runtime_signature') != kernel_signature():
        raise RuntimeError('Faiss runtime changed; the evaluation launcher must regenerate exact answers and timing budgets')
    reference = Path('/task/reference')
    for name, expected in value.get('reference_sha256', {}).items():
        if name not in ('exact_search.py', 'baseline_search.py') or digest(reference / name) != expected:
            raise RuntimeError('Reference implementation changed; restart through the evaluation launcher')
    if set(value.get('reference_sha256', {})) != {'exact_search.py', 'baseline_search.py'}:
        raise RuntimeError('Platform preparation is missing reference checksums')
    return value


if __name__ == '__main__':
    # Fail before the coding agent runs, rather than spending its budget on an
    # unsupported or stale platform. Container commands retain their normal argv.
    os.sched_setaffinity(0, select_cpus())
    load_runtime_limits()
    if len(sys.argv) > 1:
        os.execvp(sys.argv[1], sys.argv[1:])
