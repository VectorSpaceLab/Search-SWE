import argparse
import json
import os
import time
from pathlib import Path



def build(args):
    for name in ['OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS']:
        os.environ[name] = str(args.threads)
    import faiss
    import numpy as np
    started = time.monotonic()
    corpus = Path(args.corpus)
    output = Path(args.index)
    output.mkdir(parents=True, exist_ok=True)
    configuration = json.loads((corpus / "config.json").read_text())
    dimensions = configuration["dimension"]
    document_count = configuration["rows"]
    token_count = configuration["tokens"]
    offsets = np.fromfile(corpus / "offsets.i64", dtype="<i8")
    vectors = np.memmap(corpus / "vectors.f32", mode="r", dtype="<f4").reshape(-1, dimensions)
    if len(offsets) != document_count + 1 or len(vectors) != token_count:
        raise ValueError("Corpus files do not match config.json")

    faiss.omp_set_num_threads(args.threads)
    generator = np.random.default_rng(args.seed)
    sample_count = min(args.train_samples, token_count)
    sample_rows = generator.choice(token_count, size=sample_count, replace=False)
    training_vectors = np.asarray(vectors[sample_rows], dtype=np.float32, order="C")

    quantizer = faiss.IndexFlatIP(dimensions)
    ivf = faiss.IndexIVFPQ(
        quantizer,
        dimensions,
        args.nlist,
        args.subquantizers,
        args.bits,
        faiss.METRIC_INNER_PRODUCT,
    )
    ivf.cp.niter = args.coarse_iterations
    ivf.cp.max_points_per_centroid = args.max_points_per_centroid
    ivf.cp.seed = args.seed
    ivf.pq.cp.niter = args.pq_iterations
    ivf.pq.cp.seed = args.seed

    if args.opq:
        transform = faiss.OPQMatrix(dimensions, args.subquantizers)
        transform.niter = args.opq_iterations
        transform.niter_pq = args.opq_pq_iterations
        transform.max_train_points = args.opq_train_points
        index = faiss.IndexPreTransform(transform, ivf)
    else:
        index = ivf

    print(f"training index with {sample_count} vectors", flush=True)
    index.train(training_vectors)
    del training_vectors, sample_rows
    print("adding corpus vectors", flush=True)
    for start in range(0, token_count, args.add_batch):
        end = min(start + args.add_batch, token_count)
        index.add(vectors[start:end])
        if end == token_count or end % (args.add_batch * 8) == 0:
            print(f"added {end}/{token_count}", flush=True)
    if index.ntotal != token_count:
        raise ValueError(f"Index contains {index.ntotal} vectors, expected {token_count}")

    ivf_index = faiss.downcast_index(faiss.extract_index_ivf(index))
    ivf_index.nprobe = args.nprobe
    ivf_index.max_codes = args.max_codes
    ivf_index.use_precomputed_table = 0

    temporary_index = output / "tokens.faiss.tmp"
    faiss.write_index(index, str(temporary_index))
    os.replace(temporary_index, output / "tokens.faiss")

    token_documents = np.repeat(
        np.arange(document_count, dtype=np.int32), np.diff(offsets).astype(np.int64)
    )
    if len(token_documents) != token_count:
        raise ValueError("Document offsets do not cover all token vectors")
    token_documents.tofile(output / "token_doc.i32")

    metadata = {
        "rows": document_count,
        "tokens": token_count,
        "dimension": dimensions,
        "nlist": args.nlist,
        "subquantizers": args.subquantizers,
        "bits": args.bits,
        "opq": args.opq,
        "nprobe": args.nprobe,
        "max_codes": args.max_codes,
        "candidate_tokens_per_query_token": args.candidate_tokens,
        "threads": args.threads,
        "build_seconds": time.monotonic() - started,
    }
    (output / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    print(f"build complete in {metadata['build_seconds']:.1f}s", flush=True)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", default="/task/data/public/corpus")
    parser.add_argument("--index", default="/app/index")
    parser.add_argument("--nlist", type=int, default=8192)
    parser.add_argument("--subquantizers", type=int, default=32)
    parser.add_argument("--bits", type=int, default=8)
    parser.add_argument("--train-samples", type=int, default=1048576)
    parser.add_argument("--add-batch", type=int, default=131072)
    parser.add_argument("--threads", type=int, default=8)
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--coarse-iterations", type=int, default=20)
    parser.add_argument("--pq-iterations", type=int, default=18)
    parser.add_argument("--max-points-per-centroid", type=int, default=256)
    parser.add_argument("--opq", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--opq-iterations", type=int, default=16)
    parser.add_argument("--opq-pq-iterations", type=int, default=4)
    parser.add_argument("--opq-train-points", type=int, default=65536)
    parser.add_argument("--nprobe", type=int, default=5)
    parser.add_argument("--max-codes", type=int, default=0)
    parser.add_argument("--candidate-tokens", type=int, default=736)
    return parser.parse_args()


if __name__ == "__main__":
    build(parse_args())
