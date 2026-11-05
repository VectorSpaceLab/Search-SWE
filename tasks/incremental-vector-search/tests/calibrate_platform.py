"""Trusted, offline platform preparation. Never run by the coding agent."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import shutil

import grader
from kernel import prepare_targets
from runtime_limits import (BUILD_SECONDS, INSERT_SECONDS, TIMING_REPEATS,
                            digest, kernel_signature, platform_fingerprint, select_cpus)


def preparation_key():
    """Identify the machine, allocation, inputs and code behind a frozen result."""
    root = Path(__file__).resolve().parent
    manifest = json.loads(Path('/task/assets.json').read_text())
    value = {'platform': platform_fingerprint(), 'kernel': kernel_signature(),
             'assets': sorted((entry['path'], entry['size_bytes'], entry['sha256'])
                              for entry in manifest['files']),
             'code': {name: digest(root / name) for name in
                      ('calibrate_platform.py', 'grader.py', 'metrics.py', 'kernel.py',
                       'runtime_limits.py', 'process.py', 'isolate.py', 'confinement.py')},
             'references': {name: digest(Path('/task/reference') / name)
                            for name in ('exact_search.py', 'baseline_search.py')}}
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def write_reference(name):
    submission = Path('/app/submission')
    submission.mkdir(parents=True, exist_ok=True)
    (submission / 'run.sh').write_text(f'#!/bin/sh\nexec /opt/conda/bin/python /task/reference/{name}\n')
    (submission / 'run.sh').chmod(0o755)


def measure(dim, limits, *, initial_count, batch_size, stages):
    # Preparation measures each fixed reference once. TIMING_REPEATS applies
    # only to submitted implementations in the formal verifier.
    result = grader.evaluate_dataset(dim, limits, initial_count=initial_count,
                                    batch_size=batch_size, stages=stages, repeat=0)
    expected = {(stage, k) for stage in range(stages) for k in grader.KS}
    if (result.get('failure') or len(result['cells']) != len(expected)
            or {(c['stage'], c['k']) for c in result['cells']} != expected
            or len(result['insert_seconds']) != stages):
        raise RuntimeError(f'{dim}: reference preparation requires one complete valid replay')
    timed = [(result.get('build_seconds'), limits['build_seconds'])]
    timed += [(seconds, limits['insert_seconds']) for seconds in result['insert_seconds']]
    timed += [(cell['seconds'], .1 * limits['full_scan_seconds'][cell['stage']][grader.KS.index(cell['k'])])
              for cell in result['cells']]
    if any(type(seconds) not in (int, float) or not math.isfinite(seconds)
           or not 0 <= seconds <= budget for seconds, budget in timed):
        raise RuntimeError(f'{dim}: reference preparation exceeded its time budget')
    return result


def calibrate(output, *, dimensions=(1536, 3072), initial_count=105000,
              batch_size=1000, stages=10):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    fingerprint = platform_fingerprint()
    os.sched_setaffinity(0, select_cpus())
    grader.WORK.mkdir(exist_ok=True)
    grader.TRUTH = output / 'private'
    grader.LOG = output / 'diagnostics'
    grader.LOG.mkdir(parents=True, exist_ok=True, mode=0o700)
    public = output / 'public'
    public.mkdir(exist_ok=True)
    validation = output / 'validation'
    validation.mkdir(exist_ok=True)
    config = {'schema_version': 2, 'timing_repeats': TIMING_REPEATS,
              'reference_repeats': 1,
              'preparation_key': preparation_key(),
              'timing_policy': 'platform-calibrated-five-replay-median',
              'exact_scan_fraction': .10, 'minimum_baseline_missing_neighbors': 100,
              'scoring_policy': 'log-missed-neighbor-gain-over-public-reference',
              'total_requested_neighbors': stages * batch_size * sum(grader.KS),
              'cpu_count': 16, 'runtime_signature': kernel_signature(),
              'platform_fingerprint': fingerprint,
              'reference_sha256': {name: digest(Path('/task/reference') / name)
                                  for name in ('exact_search.py', 'baseline_search.py')},
              'datasets': {}}
    for dim in dimensions:
        # Copy public validation inputs, then regenerate labels with this runtime.
        # Only this public directory is mounted into the agent, never private truth.
        source = Path('/task/data/validation') / str(dim)
        destination = validation / str(dim)
        shutil.copytree(source, destination, dirs_exist_ok=True)
        prepare_targets(destination / 'initial.npy', destination / 'inserts.npy',
                        destination / 'queries.npy', destination, batch_size=100,
                        prefix='ground_truth')
        private = grader.PRIVATE / str(dim)
        target = grader.TRUTH / str(dim)
        # A shipped target is reusable only after input/runtime/file hashes match.
        target.mkdir(parents=True, exist_ok=True)
        for name in ('truth.npy', 'truth_distances.npy', 'truth-manifest.json'):
            if (private / name).exists():
                shutil.copyfile(private / name, target / name)
        truth = prepare_targets(grader.PUBLIC / str(dim) / 'initial.npy',
                                private / 'inserts.npy', private / 'queries.npy', target,
                                batch_size=batch_size, stages=stages)
        limits = {'build_seconds': BUILD_SECONDS, 'insert_seconds': INSERT_SECONDS,
                  'input_sha256': truth['input_sha256'],
                  'full_scan_seconds': [[36000.0] * 5 for _ in range(stages)]}
        write_reference('exact_search.py')
        print(f'{dim}: measuring one exact-reference replay', flush=True)
        exact = measure(dim, limits, initial_count=initial_count, batch_size=batch_size, stages=stages)
        if exact['missing_neighbors'] != 0:
            raise RuntimeError('The exact reference disagrees with prepared targets')
        grader.write_json(output / 'diagnostics' / f'{dim}.exact.json', exact)
        times = [[next(c['seconds'] for c in exact['cells'] if (c['stage'], c['k']) == (stage, k))
                  for k in grader.KS] for stage in range(stages)]
        # Measure baseline quality with ample query ceilings; report whether its
        # timings also satisfy the candidate's 10% gate, without changing it.
        limits['full_scan_seconds'] = [[t * 10 for t in row] for row in times]
        write_reference('baseline_search.py')
        print(f'{dim}: measuring one public-baseline replay', flush=True)
        baseline = measure(dim, limits, initial_count=initial_count, batch_size=batch_size, stages=stages)
        grader.write_json(output / 'diagnostics' / f'{dim}.baseline.json', baseline)
        misses = baseline['missing_neighbors']
        if misses < 100 or not 0 < baseline['micro_recall'] < 1:
            raise RuntimeError('Public baseline must leave a stable, nonzero recall gap')
        limits.update(full_scan_seconds=times, baseline_missing_neighbors=misses,
                      baseline_micro_recall=baseline['micro_recall'],
                      baseline_within_query_budget=all(c['seconds'] <= .1 * times[c['stage']][grader.KS.index(c['k'])]
                                                       for c in baseline['cells']))
        config['datasets'][str(dim)] = limits
    # The verifier's primary wrapper is 80,000 s, plus a separate 3,600 s audit.
    maximum = TIMING_REPEATS * sum(d['build_seconds'] + stages * d['insert_seconds']
                                  + .1 * sum(map(sum, d['full_scan_seconds']))
                                  for d in config['datasets'].values())
    if maximum > 78000:
        raise RuntimeError('Calibrated worst-case replay budget exceeds the verifier envelope')
    if platform_fingerprint() != fingerprint:
        raise RuntimeError('Platform allocation changed during preparation')
    (public / 'limits.json').write_text(json.dumps(config, indent=2) + '\n')
    print('Platform preparation complete; reuse these frozen limits for every model in this batch.', flush=True)
    return config


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('/platform'))
    parser.add_argument('--cache-key', action='store_true')
    args = parser.parse_args()
    if args.cache_key:
        print(preparation_key())
    else:
        calibrate(args.output)
