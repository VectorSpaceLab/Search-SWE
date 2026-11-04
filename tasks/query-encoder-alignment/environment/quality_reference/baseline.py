"""Frozen 0.6B + centered ridge quality baseline; no relevance labels used."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import time

# Set before importing torch / initializing CUDA.
os.environ["CUBLAS_WORKSPACE_CONFIG"] = ":4096:8"
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

import numpy as np
from retrieval import load_vectors, rank_scores, read_jsonl, sha256

CONFIG = {
    "version": "ridge-v1", "seed": 0, "alpha": 1.0, "center": True,
    "model_revision": "97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3",
    "max_length": 512, "batch_size": 32, "dtype": "bfloat16",
    "attention": "eager", "pooling": "last_token", "padding_side": "left",
    "corpus_prompt": "", "query_prompt": "Instruct: Given a claim, find documents that refute the claim.\nQuery:",
    "normalization": "float32 L2 before ridge and after projection",
    "fit": "all corpus rows; float64 centered sum-of-squares solve; float32 parameters",
}


def unit(x):
    x = np.asarray(x, dtype=np.float32)
    return x / np.maximum(np.linalg.norm(x, axis=1, keepdims=True), 1e-12)


def fit_ridge(x, y):
    x, y = np.asarray(x, dtype=np.float64), np.asarray(y, dtype=np.float64)
    mean_x, mean_y = x.mean(0), y.mean(0)
    xc, yc = x - mean_x, y - mean_y
    weights = np.linalg.solve(xc.T @ xc + CONFIG["alpha"] * np.eye(x.shape[1]), xc.T @ yc)
    return {"mean_x": mean_x.astype(np.float32), "mean_y": mean_y.astype(np.float32),
            "weights": weights.astype(np.float32)}


def encode(texts, model_path, prompt=""):
    import torch
    from transformers import AutoModel, AutoTokenizer
    torch.manual_seed(CONFIG["seed"])
    np.random.seed(CONFIG["seed"])
    torch.use_deterministic_algorithms(True)
    torch.set_num_threads(8)
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    tokenizer = AutoTokenizer.from_pretrained(model_path, local_files_only=True, padding_side="left")
    model = AutoModel.from_pretrained(model_path, local_files_only=True,
                                     torch_dtype=torch.bfloat16, attn_implementation="eager")
    model.requires_grad_(False).eval().to("cuda:0")
    result = []
    with torch.inference_mode():
        for start in range(0, len(texts), CONFIG["batch_size"]):
            batch = tokenizer([prompt + t for t in texts[start:start + CONFIG["batch_size"]]],
                              padding=True, truncation=True, max_length=512, return_tensors="pt").to("cuda:0")
            # Left padding guarantees the final token is non-padding.
            last = model(**batch).last_hidden_state[:, -1].float()
            result.append(torch.nn.functional.normalize(last, dim=1).cpu().numpy())
    del model
    torch.cuda.empty_cache()
    return np.concatenate(result)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--corpus", type=Path, default=Path("/task/data/corpus.jsonl"))
    p.add_argument("--doc-vectors", type=Path, required=True)
    p.add_argument("--model", type=Path, default=Path("/task/models/Qwen3-Embedding-0.6B"))
    p.add_argument("--projection", type=Path, required=True)
    p.add_argument("--fit", action="store_true")
    p.add_argument("--queries", type=Path)
    p.add_argument("--output", type=Path)
    p.add_argument("--top-k", type=int, default=1)
    args = p.parse_args()
    started = time.monotonic()
    corpus = read_jsonl(args.corpus)
    vectors = load_vectors(args.doc_vectors, corpus)
    if args.fit:
        x = encode([row["text"] for row in corpus], args.model)
        params = fit_ridge(x, vectors)
        args.projection.parent.mkdir(parents=True, exist_ok=True)
        np.savez(args.projection, **params)
        args.projection.with_suffix(".json").write_text(json.dumps({
            "config": CONFIG, "corpus_sha256": sha256(args.corpus),
            "vectors_sha256": sha256(args.doc_vectors),
            "implementation_sha256": sha256(__file__),
            "projection_sha256": sha256(args.projection),
            "fit_seconds": time.monotonic() - started,
        }, indent=2) + "\n")
    if args.queries:
        if args.output is None:
            p.error("--queries requires --output")
        queries = read_jsonl(args.queries)
        x = encode([row["text"] for row in queries], args.model, CONFIG["query_prompt"])
        with np.load(args.projection, allow_pickle=False) as params:
            projected = unit((x - params["mean_x"]) @ params["weights"] + params["mean_y"])
        rows = rank_scores(projected @ vectors.T, corpus, queries, args.top_k)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows))
    print(json.dumps({"elapsed_seconds": time.monotonic() - started, "config": CONFIG}))


if __name__ == "__main__":
    main()
