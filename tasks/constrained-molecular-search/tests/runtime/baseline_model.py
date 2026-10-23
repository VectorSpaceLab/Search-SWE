"""Author baseline: run the complete supplied GNN on public CSL structures."""
import os
for key in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS"):
    os.environ[key] = "1"

import argparse
import json
from pathlib import Path
import sys
import time

import numpy as np
import pyarrow.parquet as pq
import torch
from torch.utils.data import DataLoader, Dataset
from rdkit import RDLogger

sys.path.insert(0, "/task/runtime")
from library import Library
from apex.data.atom_bond_features import Vocabulary
from apex.data.torch_graph import PackedTorchMol, TorchMol
from apex.nn.encoder import LigandEncoder
from apex.nn.probe import LinearProbe


class Molecules(Dataset):
    def __init__(self, library, limit):
        self.library, self.limit = library, min(limit, len(library))

    def __len__(self):
        return self.limit

    def __getitem__(self, index):
        return index, TorchMol.from_smiles(self.library.id_to_smiles(index))


class LabeledMolecules(Dataset):
    def __init__(self, path, limit):
        self.smiles = pq.read_table(path, columns=["smiles"]).column("smiles").to_pylist()[:limit]

    def __len__(self):
        return len(self.smiles)

    def __getitem__(self, index):
        return index, TorchMol.from_smiles(self.smiles[index])


def initialize_worker(_):
    Vocabulary.register_atom_vocab()
    Vocabulary.register_bond_vocab()
    RDLogger.DisableLog("rdApp.*")


def collate(items):
    indexes, molecules = zip(*items)
    graphs = PackedTorchMol(list(molecules))
    # Model uses only packed tensors and the molecule count. Drop RDKit objects
    # before IPC; retain the count expected by PackedTorchMol.num_graphs.
    graphs.torch_mols = [None] * len(molecules)
    return np.asarray(indexes), graphs


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--library-dir", default="/task/library")
    parser.add_argument("--models-dir", default="/task/models")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--limit", type=int, default=1 << 60)
    parser.add_argument("--workers", type=int, default=14)
    parser.add_argument("--batch-size", type=int, default=512)
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cuda")
    parser.add_argument("--threads", type=int, default=1)
    parser.add_argument("--normalized-fragments")
    parser.add_argument("--labeled-parquet")
    args = parser.parse_args()
    torch.set_num_threads(args.threads)
    RDLogger.DisableLog("rdApp.*")
    if args.device == "cuda" and (not torch.cuda.is_available() or torch.cuda.device_count() != 1):
        raise RuntimeError("Exactly one explicitly mapped GPU is required")
    started = time.monotonic()
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    Vocabulary.register_atom_vocab()
    Vocabulary.register_bond_vocab()
    if args.labeled_parquet:
        dataset = LabeledMolecules(args.labeled_parquet, args.limit)
    else:
        library = Library(args.library_dir)
        if args.normalized_fragments:
            library.dataset.synthon_smiles = json.loads(Path(args.normalized_fragments).read_text())
        dataset = Molecules(library, args.limit)
    models = Path(args.models_dir)
    encoder = LigandEncoder.load(models / "encoder.pt", map_location="cpu").eval().to(args.device)
    probe = LinearProbe.load(models / "probe.pt", map_location="cpu").eval().to(args.device)
    names = ["score_" + target for target in ("DRD2", "ESR1", "F10", "MET", "PARP1")]
    columns = [probe.name_to_idx[name] for name in names]
    predictions = np.lib.format.open_memmap(output / "full-surrogate-scores.npy", mode="w+",
                                          dtype=np.float32, shape=(len(dataset), 5))
    embeddings = np.lib.format.open_memmap(output / "embeddings.npy", mode="w+",
                                         dtype=np.float16, shape=(len(dataset), 64))
    loader = DataLoader(dataset, batch_size=args.batch_size, num_workers=args.workers,
                        collate_fn=collate, prefetch_factor=2, multiprocessing_context="spawn", worker_init_fn=initialize_worker)
    completed = 0
    with torch.inference_mode():
        for indexes, graphs in loader:
            latent = encoder(graphs)
            scores = probe(latent)[:, columns]
            predictions[indexes] = scores.cpu().numpy()
            embeddings[indexes] = latent.cpu().numpy().astype(np.float16)
            completed += len(indexes)
            if completed % 100000 < len(indexes):
                print(completed, "of", len(dataset), "seconds", time.monotonic() - started, flush=True)
    predictions.flush()
    embeddings.flush()
    if args.device == "cuda":
        torch.cuda.synchronize()
    result = {"seconds": time.monotonic() - started, "n_products": len(dataset),
              "workers": args.workers, "batch_size": args.batch_size,
              "device": args.device, "threads": args.threads,
              "gpu": torch.cuda.get_device_name(0) if args.device == "cuda" else None,
              "peak_gpu_allocated_bytes": torch.cuda.max_memory_allocated() if args.device == "cuda" else 0,
              "normalized_fragments": bool(args.normalized_fragments),
              "container_memory_peak_bytes": int(Path("/sys/fs/cgroup/memory.peak").read_text()),
              "cpu_max": Path("/sys/fs/cgroup/cpu.max").read_text().strip(),
              "source": "full supplied encoder+probe; public definitions only"}
    (output / "measurement.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
