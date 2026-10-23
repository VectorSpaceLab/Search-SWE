"""Fit a simple baseline on public candidates, with no query/test supervision."""
import argparse
import json
from pathlib import Path
import shutil

import numpy as np


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", default="/task/data/corpus")
    parser.add_argument("--output", default="/app/submission")
    parser.add_argument("--method", choices=["identity", "language-center", "pc", "whiten"], required=True)
    parser.add_argument("--alpha", type=float, default=.75)
    parser.add_argument("--components", type=int, default=16)
    parser.add_argument("--regularization", type=float, default=.1)
    args = parser.parse_args()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    data, languages = [], []
    for dataset in ("belebele", "xquad"):
        directory = Path(args.corpus) / dataset
        metadata = [json.loads(s) for s in (directory / "documents.jsonl").read_text().splitlines()]
        data.append(np.load(directory / "vectors.npy", allow_pickle=False).astype(np.float32))
        languages.extend(row["language"] for row in metadata)
    data = np.concatenate(data)
    languages = np.array(languages)
    weights = {}
    specification = dict(method=args.method, statistics_source="complete public candidate pools")
    if args.method == "language-center":
        order = sorted(set(languages))
        weights["means"] = np.stack([data[languages == language].mean(0) for language in order])
        specification.update(languages=order, alpha=args.alpha)
    elif args.method in {"pc", "whiten"}:
        mean = data.mean(0)
        centered = data - mean
        eigenvalues, axes = np.linalg.eigh(centered.T @ centered / len(data))
        if args.method == "pc":
            if not 0 <= args.components < 1024:
                raise ValueError("Invalid principal-component count")
            matrix = np.eye(1024, dtype=np.float32)
            if args.components:
                top = axes[:, -args.components:]
                matrix -= top @ top.T
            specification["components"] = args.components
        else:
            if args.regularization <= 0:
                raise ValueError("Whitening regularization must be positive")
            matrix = axes * (np.maximum(eigenvalues, 0) + args.regularization * eigenvalues.max()) ** -.5
            specification["regularization"] = args.regularization
        weights.update(mean=mean, matrix=matrix.astype(np.float32))
    np.savez(output / "parameters.npz", **weights)
    (output / "spec.json").write_text(json.dumps(specification, indent=2) + "\n")
    shutil.copyfile(Path(__file__).with_name("transform.py"), output / "transform.py")


if __name__ == "__main__":
    main()
