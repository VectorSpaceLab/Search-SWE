"""Baseline-only exact descriptors from PUBLIC definitions; no target labels read."""
import os

for name in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS"):
    os.environ[name] = "1"
os.sched_setaffinity(0, sorted(os.sched_getaffinity(0))[-16:])

import concurrent.futures
import argparse
import hashlib
import itertools
import json
import multiprocessing
from pathlib import Path
import sys
import time

import numpy as np
from rdkit import Chem, RDLogger
from rdkit.Chem import Descriptors, Crippen, Lipinski, rdMolDescriptors

from library import Library

LIBRARY = None
FRAGMENTS = None


def process(job):
    reaction, start, stop = job
    groups = LIBRARY.tree[reaction]
    combinations = itertools.product(*([FRAGMENTS[i] for i in group] for group in groups))
    properties = np.full((stop - start, 6), np.nan, dtype=np.float32)
    canonical = np.zeros(stop - start, dtype="V16")
    invalid = []
    for i, components in enumerate(itertools.islice(combinations, start, stop)):
        smiles = ".".join(components)
        molecule = Chem.MolFromSmiles(smiles)
        if molecule is None:
            invalid.append(int(LIBRARY.offsets[reaction] + start + i))
            continue
        properties[i] = [Descriptors.MolWt(molecule), Crippen.MolLogP(molecule),
                         Lipinski.NumHDonors(molecule), Lipinski.NumHAcceptors(molecule),
                         Lipinski.NumRotatableBonds(molecule), rdMolDescriptors.CalcTPSA(molecule)]
        normalized = Chem.MolToSmiles(molecule, canonical=True, isomericSmiles=True)
        canonical[i] = hashlib.blake2b(normalized.encode(), digest_size=16).digest()
    return int(LIBRARY.offsets[reaction] + start), properties, canonical, invalid


def main():
    global LIBRARY, FRAGMENTS
    RDLogger.DisableLog("rdApp.*")
    parser = argparse.ArgumentParser()
    parser.add_argument("--normalized-fragments")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--library-dir", default="/task/library")
    args = parser.parse_args()
    started = time.monotonic()
    out = Path(args.output_dir)
    out.mkdir(exist_ok=True)
    LIBRARY = Library(args.library_dir)
    FRAGMENTS = (json.loads(Path(args.normalized_fragments).read_text()) if args.normalized_fragments
                 else [s.split(".")[0] for s in LIBRARY.dataset.synthon_smiles])
    if len(FRAGMENTS) != LIBRARY.dataset.num_synthons:
        raise ValueError("Wrong normalized fragment cache size")
    properties = np.lib.format.open_memmap(out / "properties.npy", mode="w+", dtype=np.float32,
                                         shape=(len(LIBRARY), 6))
    canonical = np.lib.format.open_memmap(out / "canonical-hashes.npy", mode="w+", dtype="V16",
                                        shape=(len(LIBRARY),))
    jobs = [(r, start, min(start + 16384, int(size)))
            for r, size in enumerate(np.diff(LIBRARY.offsets))
            for start in range(0, int(size), 16384)]
    invalid, completed = [], 0
    with concurrent.futures.ProcessPoolExecutor(max_workers=16,
            mp_context=multiprocessing.get_context("fork")) as pool:
        for offset, values, hashes, bad in pool.map(process, jobs):
            properties[offset:offset + len(values)] = values
            canonical[offset:offset + len(hashes)] = hashes
            invalid.extend(bad)
            completed += len(values)
            if completed % 500000 < len(values):
                print(completed, "of", len(LIBRARY), "seconds", time.monotonic() - started, flush=True)
    properties.flush()
    canonical.flush()
    report = {"source": "public reactions/synthons only", "products": len(LIBRARY),
              "normalized_fragments": args.normalized_fragments,
              "seconds": time.monotonic() - started, "invalid_structures": invalid,
              "cpu_affinity": sorted(os.sched_getaffinity(0)), "workers": 16,
              "properties": ["mol_wt", "logp", "n_hbd", "n_hba", "n_rotatable_bonds", "tpsa"]}
    report["container_memory_peak_bytes"] = int(Path("/sys/fs/cgroup/memory.peak").read_text())
    report["memory_max"] = Path("/sys/fs/cgroup/memory.max").read_text().strip()
    report["cpu_max"] = Path("/sys/fs/cgroup/cpu.max").read_text().strip()
    (out / "measurement.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report), flush=True)


if __name__ == "__main__":
    main()
