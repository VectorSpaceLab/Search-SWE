"""Prepare exact float32 targets using the current runtime, with checked inputs."""
import json
from pathlib import Path
import tempfile

import faiss
import numpy as np

from runtime_limits import digest, kernel_signature, select_cpus


def input_hashes(initial, inserts, queries):
    return {name: digest(path) for name, path in
            (('initial', initial), ('inserts', inserts), ('queries', queries))}


def require_truth_kernel(private):
    manifest = json.loads((Path(private) / 'truth-manifest.json').read_text())
    if manifest.get('runtime_signature') != kernel_signature():
        raise RuntimeError('Exact targets use a different Faiss runtime; restart through the evaluation launcher to regenerate them')


def prepare_targets(initial, inserts, queries, output, *, batch_size, stages=10,
                    prefix='truth', threads=None):
    """Cache only targets matching every input byte and the active Faiss kernel."""
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    manifest_path = output / f'{prefix}-manifest.json'
    inputs = input_hashes(initial, inserts, queries)
    signature = kernel_signature()
    try:
        previous = json.loads(manifest_path.read_text())
        if (previous.get('input_sha256') == inputs and previous.get('runtime_signature') == signature
                and previous.get('batch_size') == batch_size and previous.get('stages') == stages
                and len(previous.get('files', [])) == 2
                and all(digest(output / e['path']) == e['sha256'] for e in previous['files'])):
            return previous
    except (OSError, ValueError, KeyError):
        pass
    base = np.load(initial, mmap_mode='r', allow_pickle=False)
    updates = np.load(inserts, mmap_mode='r', allow_pickle=False)
    probes = np.load(queries, mmap_mode='r', allow_pickle=False)
    if (base.dtype != np.float32 or updates.dtype != np.float32 or probes.dtype != np.float32
            or base.ndim != 2 or updates.shape != probes.shape
            or probes.shape != (batch_size * stages, base.shape[1])
            or len(base) + batch_size < 1000):
        raise ValueError('Unexpected exact-target input shapes or precision')
    faiss.cvar.distance_compute_blas_threshold = 2_147_483_647
    faiss.omp_set_num_threads(threads if threads is not None else len(select_cpus()))
    index = faiss.IndexFlatL2(base.shape[1])
    index.add(base)
    with tempfile.TemporaryDirectory(prefix='.targets-', dir=output) as temporary:
        temporary = Path(temporary)
        names = (f'{prefix}.npy', f'{prefix}_distances.npy')
        target = np.lib.format.open_memmap(temporary / names[0], mode='w+', dtype='<i8', shape=(len(probes), 1000))
        distances = np.lib.format.open_memmap(temporary / names[1], mode='w+', dtype='<f4', shape=target.shape)
        for stage in range(stages):
            lo, hi = stage * batch_size, (stage + 1) * batch_size
            index.add(updates[lo:hi])
            distances[lo:hi], target[lo:hi] = index.search(np.asarray(probes[lo:hi]), 1000)
        target.flush()
        distances.flush()
        del target, distances
        files = [{'path': name, 'size_bytes': (temporary / name).stat().st_size,
                  'sha256': digest(temporary / name)} for name in names]
        manifest = {'schema_version': 2, 'runtime_signature': signature,
                    'input_sha256': inputs, 'batch_size': batch_size, 'stages': stages,
                    'kernel': 'IndexFlatL2 direct float32', 'files': files}
        for name in names:
            (temporary / name).replace(output / name)
        (temporary / manifest_path.name).write_text(json.dumps(manifest, indent=2) + '\n')
        (temporary / manifest_path.name).replace(manifest_path)
    return manifest
