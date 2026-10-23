"""Training-feature index for the provided retrieval baselines."""

import json

import numpy as np
import torch
from transformers import AutoTokenizer

from candidate_features import FEATURE_NAMES, TrainingFeatures
from fixed_features import load_training_array


def sha256(path):
    import hashlib
    with path.open("rb") as stream:
        return hashlib.file_digest(stream,"sha256").hexdigest()


class Retriever:
    def __init__(self, args):
        self.mode = args.mode
        self.rows = [json.loads(line) for line in (args.data_dir / "train.jsonl").read_text().splitlines()]
        self.ids = [r["id"] for r in self.rows]
        self.order = np.array(self.ids)
        tokenizer = AutoTokenizer.from_pretrained(args.model_dir / "base", local_files_only=True)
        self.base_nll = None
        if args.base_nll:
            complete = json.loads((args.base_nll.parent / "complete.json").read_text())
            if complete["training_sha256"] != sha256(args.data_dir / "train.jsonl"):
                raise ValueError("Base token features belong to a different training corpus")
            if complete["base_manifest_sha256"] != sha256(args.model_dir / "base/verified-manifest.json"):
                raise ValueError("Base token features belong to a different base model")
            if (json.loads((args.base_nll.parent / "row-ids.json").read_text()) != self.ids
                    or complete["losses_sha256"] != sha256(args.base_nll)):
                raise ValueError("Base token features have wrong row IDs or checksum")
            self.base_nll = load_training_array(args.base_nll)
            if self.base_nll.shape != (len(self.rows), 512):
                raise ValueError("Invalid base token feature shape")
        if self.mode.startswith("base-nll") and self.base_nll is None:
            raise ValueError("This baseline requires a frozen base-token NLL feature file")
        loss_path = args.data_dir / "train-response-loss.npy"
        trained_loss = np.load(loss_path, mmap_mode="r", allow_pickle=False) if loss_path.exists() else None
        if trained_loss is not None and (trained_loss.shape != (len(self.ids),) or not np.isfinite(trained_loss).all()):
            raise ValueError("Invalid training response loss features")
        self.training = TrainingFeatures(self.rows, tokenizer, self.base_nll, trained_loss)
        self.coherence = None
        alternatives_path = getattr(args, "base_alternatives", None)
        if alternatives_path:
            from source_coherence import SourceCoherence
            complete = json.loads((alternatives_path.parent / "complete.json").read_text())
            if (self.base_nll is None
                    or complete["training_sha256"] != sha256(args.data_dir / "train.jsonl")
                    or complete["base_manifest_sha256"] != sha256(args.model_dir / "base/verified-manifest.json")
                    or complete["base_nll_sha256"] != sha256(args.base_nll)
                    or complete["alternatives_sha256"] != sha256(alternatives_path)
                    or json.loads((alternatives_path.parent / "row-ids.json").read_text()) != self.ids):
                raise ValueError("Base alternatives do not match training text, base, NLL cache or row IDs")
            alternatives = load_training_array(alternatives_path)
            if alternatives.shape != (len(self.ids), 512) or alternatives.dtype != np.int32:
                raise ValueError("Invalid base alternatives shape or dtype")
            self.coherence = SourceCoherence(self.training, alternatives)
        if (self.mode.startswith("source-") or self.mode == "query-source-text") and self.coherence is None:
            raise ValueError("Source-coherence baselines require training-only base alternatives")
        self.bm25 = None
        if self.mode in {"bm25", "bm25-target"}:
            from rank_bm25 import BM25Okapi
            self.bm25 = BM25Okapi([self.text_tokens(r["instruction"]+" "+r["input"]+" "+r["output"]) for r in self.rows])
        self.model = None
        self.ranker = None
        if self.mode == "entity-ranker":
            if not args.ranker:
                raise ValueError("Ranker mode needs a frozen ranker artifact")
            import joblib
            record = joblib.load(args.ranker)
            if record["feature_names"] != FEATURE_NAMES:
                raise ValueError("Ranker feature schema mismatch")
            self.ranker = record["model"]

    @staticmethod
    def text_tokens(text):
        import re
        return re.findall(r"[a-z0-9]+", text.lower())

    def rank(self, query, action="query"):
        indices, features = self.training.query_features(query)
        if action == "features":
            return {"query_id": query["id"], "candidate_ids": [self.ids[i] for i in indices],
                    "feature_names": FEATURE_NAMES, "features": features.tolist()}
        if self.mode in {"bm25", "bm25-target"}:
            text = query["target_text"] if self.mode == "bm25-target" else query["instruction"]+" "+query["input"]+" "+query["generated_answer"]
            score = self.bm25.get_scores(self.text_tokens(text))
            indices = np.arange(len(self.ids))
        elif self.mode == "query-source-text":
            source_indices, context = self.coherence.context_features(query)
            if not np.array_equal(indices, source_indices):
                raise ValueError("Source lexical candidate order mismatch")
            score, _ = self.coherence.lexical_scores(context, features[:, 5])
        elif self.mode.startswith("source-"):
            pool = self.coherence.pool(query["target_text"])
            indices, score = pool["indices"], pool[self.mode]
        elif self.mode in {"target", "frequency", "prompt-absent", "base-nll-mean", "base-nll-max", "entity-ranker"}:
            if self.mode == "target":
                score = np.zeros(len(indices))
            elif self.mode == "frequency":
                score = features[:, 0]
            elif self.mode == "prompt-absent":
                score = -features[:, 1]
            elif self.mode == "base-nll-mean":
                score = features[:, 4] - (1-features[:, 3])*1e6
            elif self.mode == "base-nll-max":
                score = features[:, 5] - (1-features[:, 3])*1e6
            else:
                score = self.ranker.predict_proba(features)[:, 1]
        else:
            raise ValueError("Unknown retrieval mode")
        order = np.lexsort((self.order[indices], -np.asarray(score, dtype=np.float64)))[:10]
        return {"query_id": query["id"], "ids": [self.ids[indices[i]] for i in order]}

