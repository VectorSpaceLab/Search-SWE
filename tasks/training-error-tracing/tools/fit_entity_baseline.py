"""Fit the prompt-independent baseline using only public development labels."""

import argparse
import hashlib
import json
import time
from pathlib import Path
from types import SimpleNamespace

import joblib
import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer

from candidate_features import FEATURE_NAMES


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def make_model(config):
    return Pipeline([("columns", FunctionTransformer(np.take, kw_args={"indices": config["columns"], "axis": 1})),
                     ("classifier", HistGradientBoostingClassifier(
                         max_iter=100, learning_rate=.05, max_depth=config["depth"],
                         l2_regularization=config["l2"], min_samples_leaf=20,
                         max_bins=64, early_stopping=False, random_state=20261019))])


def training_arrays(rows, labels, qgroups):
    arrays, answers, weights = [], [], []
    counts = {g: sum(qgroups[r["query_id"]] == g for r in rows) for g in labels}
    for row in rows:
        gid = qgroups[row["query_id"]]
        arrays.append(np.asarray(row["features"], dtype=np.float32))
        answers.extend(int(i in labels[gid]["record_ids"]) for i in row["candidate_ids"])
        weights.extend([1/(counts[gid]*len(row["candidate_ids"]))]*len(row["candidate_ids"]))
    weights = np.asarray(weights)
    return np.concatenate(arrays), np.asarray(answers), weights/weights.mean()


def p10(model, row, relevant):
    scores = model.predict_proba(np.asarray(row["features"], dtype=np.float32))[:, 1]
    indices = np.lexsort((np.asarray(row["candidate_ids"]), -scores))[:10]
    return sum(row["candidate_ids"][i] in relevant for i in indices)/10


def entity_folds(labels):
    """Keep every group sharing an error entity in the same validation fold."""
    folds = {}
    for gid, group in sorted(labels.items()):
        folds.setdefault(group["error_entity"].strip().casefold(), []).append(gid)
    return list(folds.values())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--base-nll", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.output_dir.exists():
        raise ValueError("Use a fresh ranker output directory")
    started = time.monotonic()
    from retrieval_index import Retriever
    metadata = json.loads((args.base_nll.parent / "complete.json").read_text())
    retriever = Retriever(SimpleNamespace(mode="frequency", data_dir=args.data_dir,
                                         model_dir=args.model_dir, base_nll=args.base_nll, ranker=None))
    if json.loads((args.base_nll.parent / "row-ids.json").read_text()) != retriever.ids:
        raise ValueError("Training cache has a different row mapping")
    labels = json.loads((args.data_dir / "dev-labels.json").read_text())
    if len(labels) != 5:
        raise ValueError("Expected the five public development groups")
    rows, qgroups = [], {}
    for gid, group in labels.items():
        indices, fixed = retriever.training.pool(group["error_entity"])
        features = np.column_stack([fixed, np.zeros((len(indices), 2), dtype=np.float32)])
        for qid in group["query_ids"]:
            qgroups[qid] = gid
            rows.append({"query_id": qid, "candidate_ids": [retriever.ids[i] for i in indices],
                         "features": features})
    rows.sort(key=lambda r: r["query_id"])
    configs = [{"columns": list(range(7)), "depth": depth, "l2": l2}
               for depth in [2, 3] for l2 in [1, 10]]
    trials = []
    for config in configs:
        scores = {}
        for held_groups in entity_folds(labels):
            fitting = [r for r in rows if qgroups[r["query_id"]] not in held_groups]
            x, y, weight = training_arrays(fitting, labels, qgroups)
            model = make_model(config).fit(x, y, classifier__sample_weight=weight)
            for held in held_groups:
                scores[held] = float(np.mean([p10(model, r, set(labels[held]["record_ids"]))
                                             for r in rows if qgroups[r["query_id"]] == held]))
        trials.append({"configuration": config, "held_group_p10": scores,
                       "group_macro_p10": float(np.mean(list(scores.values())))})
    best = max(range(len(trials)), key=lambda i: (trials[i]["group_macro_p10"], -i))
    x, y, weight = training_arrays(rows, labels, qgroups)
    model = make_model(configs[best]).fit(x, y, classifier__sample_weight=weight)
    args.output_dir.mkdir(parents=True)
    path = args.output_dir / "entity-ranker.joblib"
    joblib.dump({"feature_names": FEATURE_NAMES, "model": model, "query_independent": True}, path)
    (args.output_dir / "training-report.json").write_text(json.dumps(
        {"model_sha256": sha256(path), "configuration": configs[best], "selection_results": trials,
         "public_dev_labels_sha256": sha256(args.data_dir / "dev-labels.json"),
         "training_sha256": metadata["training_sha256"], "base_nll_sha256": sha256(args.base_nll),
         "test_queries_or_labels_used": False, "query_features_used": False,
         "selection_unit": "whole shared-error-entity family",
         "elapsed_sec": time.monotonic()-started}, indent=2)+"\n")
    print(json.dumps({"selected_configuration": configs[best], "elapsed_sec": time.monotonic()-started}))


if __name__ == "__main__":
    main()
