# Environment

Python 3.12 is at /opt/conda/bin/python. The shared GPU image contains CUDA
PyTorch, Transformers, SentenceTransformers, FlagEmbedding, NumPy and FAISS.
Both stages have 8 CPU cores, 32 GiB RAM, 100 GiB storage and one NVIDIA GPU.
Development lasts at most 6 hours; task verification at most 70 minutes,
within a 95-minute verifier including an independently bounded integrity judge.

/task/data and /task/models are read-only. data/doc.npy contains 8,674 by 2,560
float32 vectors; corpus.jsonl supplies the matching row identities and texts.
Public queries and labels are in data/validation. Hidden queries and labels
are never mounted into the agent environment. Do not alter document vectors.

/app/quality_baseline contains the frozen 0.6B ridge quality baseline and its
reproduction instructions. /app/starter contains the 4B time reference. The
4B model is readable during development but not by the unprivileged final
submission; the final backbone must derive from the supplied 0.6B model.
All custom files needed at inference must be under /app/submission. Its copied
runtime is read-only; use the writable output directory or TMPDIR for scratch.

Each reference or candidate process has an 1,800-second hard timeout. Reference
and candidate timing includes interpreter/imports, model loading, all query
encoding, fixed-vector loading/search, filtering, output and exit. The verifier
measures with a monotonic external clock and event-driven exit waiting. It
runs the quality reference first, then the 4B time reference, then the candidate.
There is no query or model warmup. OS file caches are not flushed; private
reference predictions are inaccessible. The first candidate run sets its time;
a fresh second process checks byte-identical output, with separate scratch.
The candidate must take at most 60% of the 4B reference's elapsed time.
Both references and candidate use the same GPU and outer CPU/RAM limits.
