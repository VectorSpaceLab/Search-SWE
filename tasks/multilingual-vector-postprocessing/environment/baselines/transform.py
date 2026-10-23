"""Frozen simple-vector baselines; optional, not a required solver algorithm."""
import json
from pathlib import Path
import numpy as np


def load(submission_dir):
    root = Path(submission_dir)
    specification = json.loads((root / "spec.json").read_text())
    weights = np.load(root / "parameters.npz", allow_pickle=False)
    return specification, weights


def transform(vectors, languages, state):
    specification, weights = state
    method = specification["method"]
    if method == "identity":
        return vectors.copy()
    if method == "language-center":
        means = weights["means"]
        order = specification["languages"]
        index = np.array([order.index(language) for language in languages])
        return vectors - specification["alpha"] * means[index]
    return (vectors - weights["mean"]) @ weights["matrix"]
