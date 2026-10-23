#!/usr/bin/env python3
"""Derive phase-specific inputs from the two checksum-pinned TexMex archives."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import tarfile

import numpy as np

PUBLIC_QUERY_COUNT = 10


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(8 << 20), b''):
            h.update(block)
    return h.hexdigest()


def main():
    if np.__version__ != '2.5.2':
        raise RuntimeError('Prepare the fixed split with NumPy 2.5.2 from the documented environment')
    os.umask(0o022)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--task-root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--split', choices=['learn', 'query'], required=True)
    args = parser.parse_args()
    root = args.task_root
    manifest = json.loads((root / 'assets.json').read_text())
    entries = {Path(e['path']).name: e for e in manifest['files']}
    output = {'schema_version': 1, 'split': args.split, 'sources': manifest, 'datasets': {}}
    for name, dim, nq, seed in [('sift', 128, 5000, 240216), ('gist', 960, 1000, 240217)]:
        archive = root / 'data/source' / (name + '.tar.gz')
        entry = entries[archive.name]
        if archive.stat().st_size != entry['size_bytes'] or digest(archive) != entry['sha256']:
            raise ValueError(f'Archive integrity failure: {archive}')
        public = root / 'data/public' / name
        private = root / 'data/verifier' / name
        public.mkdir(parents=True, exist_ok=True)
        private.mkdir(parents=True, exist_ok=True, mode=0o700)
        (root / 'data/public').chmod(0o755)
        public.chmod(0o755)
        (root / 'data/verifier').chmod(0o700)
        private.chmod(0o700)
        extracted = {}
        with tarfile.open(archive, 'r|gz') as tar:
            for member in tar:
                kind = next((k for k in ['base', 'learn', 'query'] if member.name.endswith(f'/{name}_{k}.fvecs')), None)
                if kind is None:
                    continue
                if not member.isfile():
                    raise ValueError('Expected regular vector file')
                # Read only the vectors needed from learn; tar streaming discards the rest.
                count = member.size // (4 * (dim + 1))
                keep = min(count, PUBLIC_QUERY_COUNT) if kind == 'learn' else count
                stream = tar.extractfile(member)
                if kind == 'base':
                    target = public / 'base.f32'
                    with target.open('wb') as f:
                        left = count
                        while left:
                            take = min(left, 8192)
                            raw = stream.read(take * (dim + 1) * 4)
                            a = np.frombuffer(raw, dtype='<f4').reshape(take, dim + 1)
                            if not np.all(a[:, 0].view('<i4') == dim):
                                raise ValueError('Invalid fvecs dimensions')
                            np.ascontiguousarray(a[:, 1:]).tofile(f)
                            left -= take
                    if count != 1_000_000:
                        raise ValueError('Expected one million base vectors')
                else:
                    a = np.frombuffer(stream.read(keep * (dim + 1) * 4), dtype='<f4').reshape(keep, dim + 1)
                    if not np.all(a[:, 0].view('<i4') == dim):
                        raise ValueError('Invalid fvecs dimensions')
                    extracted[kind] = a[:, 1:].copy()
        rng = np.random.Generator(np.random.PCG64(seed))
        order = rng.permutation(len(extracted['query']))[:nq]
        if args.split == 'query':
            dev_count = PUBLIC_QUERY_COUNT
            calibration = extracted['query'][order[:dev_count]]
            queries = extracted['query'][order[dev_count:]]
        else:
            calibration = extracted['learn']
            queries = extracted['query'][order]
        calibration.tofile(public / 'calibration.f32')
        queries.tofile(private / 'queries.f32')
        # Independent public and hidden deletion permutations. Hidden order is not exposed.
        for path, s in [(public / 'deletions.i32', seed + 100), (private / 'deletions.i32', seed + 200)]:
            np.random.Generator(np.random.PCG64(s)).permutation(1_000_000)[:800_000].astype('<i4').tofile(path)
        config = {'dataset': name, 'rows': 1_000_000, 'dimension': dim,
                  'dtype': '<f4', 'metric': 'squared_l2', 'stages': 100,
                  'delete_batch': 8000, 'top_k': 10,
                  'calibration_count': len(calibration), 'test_query_count': len(queries)}
        (public / 'config.json').write_text(json.dumps(config, indent=2) + '\n')
        records = []
        for folder in [public, private]:
            for p in sorted(folder.iterdir()):
                if p.is_file() and p.name != 'truth.i32':
                    p.chmod(0o644 if folder == public else 0o600)
                    records.append({'path': str(p.relative_to(root)), 'size_bytes': p.stat().st_size, 'sha256': digest(p)})
        output['datasets'][name] = {'config': config, 'files': records}
        print(json.dumps({'dataset': name, 'config': config}), flush=True)
    target = root / 'data/prepared-manifest.json'
    target.write_text(json.dumps(output, indent=2) + '\n')
    print(f'Prepared inputs: {target}', flush=True)


if __name__ == '__main__':
    main()
