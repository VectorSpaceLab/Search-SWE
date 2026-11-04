"""Prepare a complete feedback-baseline submission from public development data."""
import argparse
import csv
import pickle
import shutil
import tempfile
from pathlib import Path

import faiss
import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from threadpoolctl import threadpool_limits

from feedback_baseline import Engine, build


def prepare(data_dir, output_dir, threads=15):
    if not 1 <= threads <= 15:
        raise ValueError("threads must be between 1 and 15")
    output_dir.mkdir(parents=True, exist_ok=True)
    if any(output_dir.iterdir()):
        raise ValueError("output-dir must be empty")
    import json
    queries = [json.loads(line) for line in (data_dir / "dev-queries.jsonl").read_text().splitlines()]
    if len(queries) != 500:
        raise ValueError("Expected 500 public development queries")
    with (data_dir / "dev-qrels.tsv").open() as stream:
        labels = {row["query-id"]: int(row["corpus-id"][3:])
                  for row in csv.DictReader(stream, delimiter="\t")}
    matrices, positions = [], []
    with tempfile.TemporaryDirectory(prefix=".training-", dir=output_dir) as temporary:
        index_dir = Path(temporary)
        with threadpool_limits(limits=threads):
            faiss.omp_set_num_threads(threads)
            build(data_dir, index_dir)
            engine = Engine(data_dir, index_dir)
            faiss.omp_set_num_threads(threads)
            for query in queries:
                result = engine.retrieve(query["text"], query["vector"])
                rows = result["rows"]
                matches = np.flatnonzero(rows == labels[query["query_id"]])
                if len(matches):
                    matrices.append(engine.features(result, rows))
                    positions.append(int(matches[0]))
            lengths = np.array([len(matrix) for matrix in matrices])
            starts = np.r_[0, np.cumsum(lengths)[:-1]]
            features = np.concatenate(matrices).astype("f8")
            targets = np.zeros(len(features), dtype="i4")
            targets[starts + positions] = 1
            positives = int(targets.sum())
            weights = np.where(targets == 1, len(features) / (2 * positives),
                               len(features) / (2 * (len(features) - positives)))
            model = HistGradientBoostingClassifier(
                max_leaf_nodes=7, max_iter=120, learning_rate=.05,
                l2_regularization=1., early_stopping=False, random_state=17)
            model.fit(features, targets, sample_weight=weights)
            (output_dir / "model.pkl").write_bytes(pickle.dumps(model, protocol=5))
            engine.db.close()
    shutil.copyfile(Path(__file__).with_name("feedback_baseline.py"),
                    output_dir / "feedback_baseline.py")
    wrapper = """#!/bin/sh
set -eu
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
exec /opt/conda/bin/python "$(dirname "$0")/feedback_baseline.py" "$@"
"""
    (output_dir / "search.sh").write_text(wrapper)
    (output_dir / "search.sh").chmod(0o755)
    return len(matrices)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--threads", type=int, default=15)
    args = parser.parse_args()
    groups = prepare(args.data_dir, args.output_dir, args.threads)
    print(f"Prepared {args.output_dir} using {groups} public query groups")


if __name__ == "__main__":
    main()
