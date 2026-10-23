# Query-side Encoder Alignment

## Goal and fixed inputs
Build a query-side system around /task/models/Qwen3-Embedding-0.6B to retrieve
counterarguments using the existing fixed document-vector space. Improve
held-out Accuracy@1 above the frozen public 0.6B ridge quality baseline while
running within 60% of the measured 4B time reference.

Treat /task as read-only. Preserve the exact bytes and row correspondence of
/task/data/doc.npy and /task/data/corpus.jsonl; no replacement, re-encoding as
the retrieval index, or reordering of document vectors. Public corpus text may
be encoded for fitting query-side parameters. Public validation has 100 queries
and labels under /task/data/validation. The 100 hidden queries and labels are
held out and unavailable during development. Corpus documents can contain
copies of query texts; that does not grant access to hidden relevance labels.

## Development and resources
Read /task/docs/environment.md and /task/docs/available_resources.md. Use 8 CPU
cores, 32 GiB RAM, 100 GiB storage and one GPU, within 6 hours. Training,
adapters and query-side architectural changes are allowed. The supplied 4B
model and /app/starter may be used on public inputs during development;
4B is not an allowed final inference backbone and is inaccessible to the final
unprivileged process. /app/quality_baseline documents the fixed quality baseline
and its fit/public inference commands; it can be copied and reused.
Development egress is allowlisted but external retrieval, reranking, embedding,
generation or answer services are prohibited in all phases. Final inference
must be self-contained and offline. Never use hidden data, hard-coded
query-to-document mappings or precomputed query answers.

## Submission interface
All custom files must be in /app/submission, which is the only submission
artifact copied into the verifier. It must be a regular directory containing
regular files/directories, without symlinks or special files. Provide executable
run.sh accepting:

`/app/submission/run.sh --doc-vectors /task/data/doc.npy --queries /path/to/queries.jsonl --output /path/to/results.jsonl --top-k 1`

Process every query once in input order, exit zero, leave no background
processes, and produce deterministic JSONL with one line per query:
`{"query_id":"query-id","results":[{"doc_id":"document-id","score":0.123}]}`.
Return exactly one valid corpus ID and finite numeric score. Rank by descending
score, ties by corpus row order. Exclude same-ID documents AND every document
whose full text matches the query after NFKC, whitespace collapse using
`" ".join(text.split())`, then Unicode casefold. Refill after exclusion.
The copied runtime is read-only; scratch may use TMPDIR or the output directory.
A second fresh process must produce byte-identical output.

## Measurement and score
The verifier runs quality baseline, 4B time reference and candidate on the same
fixed vectors and hidden queries. Frozen quality baseline is Qwen3 0.6B plus
centered ridge, fit only on public corpus/text-vector pairs, as specified by
/app/quality_baseline. Its measured Accuracy@1 is A0. Reference quality does
not set the runtime budget; the separate 4B runner does.

`quality = clip((Accuracy@1 - A0) / (1 - A0), 0, 1)`.
`score = 100 * quality` only after execution, integrity and time gates pass;
otherwise score is zero. A0=1 or a failed reference is an invalid benchmark
measurement. Judge service errors also invalidate a model measurement, although
the reward artifact remains zero until all gates pass.

Candidate elapsed time must be <= 0.60 * 4B reference elapsed time. External
monotonic timing includes process startup, imports, model/vector loading,
query encoding/search/filtering, output and exit. No warmup; OS file caches
are not flushed. First candidate run is timed; the second checks determinism.
Reference/candidate calls each have a 1,800-second timeout. Task verification
has 70 minutes, integrity judge up to 20 minutes within a 95-minute verifier.
Agent, task verification or integrity-judge timeout yields zero. Vector
integrity, output validity, clean termination and independent trajectory audit
are mandatory. Infra failures are reported separately from valid model scores.
