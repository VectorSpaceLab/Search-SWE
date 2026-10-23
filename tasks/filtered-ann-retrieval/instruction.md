I need to find the nearest vectors among records that contain all requested tags. Please build an executable, persistent Faiss search system that returns the exact filtered Top-10 using squared Euclidean distance on the supplied vectors.

The corpus is under `/task/data/corpus`, public queries and reference answers are under `/task/data/validation`, and a small example is under `/task/data/example`. Read `/task/docs/environment.md`, `/task/docs/available_resources.md` and `/task/docs/data-format.md` for the runtime, resource restrictions and binary file formats.

You have 120 minutes to complete the task. Keep all submission files under `/app`; `/task` is read-only. Verification runs in a separate environment as a non-root user with `/app` read-only. Provide these executable entry points:

```bash
/app/build.sh \
  --vectors /task/data/corpus/vectors.u8bin \
  --metadata /task/data/corpus/metadata.spmat \
  --index-dir /path/to/index
```

The build must exit successfully within **600 seconds** and save a valid Faiss ANN index covering the supplied corpus as `index.faiss`. The index must use L2, be readable by `faiss.read_index`, and be used during retrieval. Full-corpus brute-force search must not be the default query strategy.

Store all required runtime state as regular files inside the supplied index directory. The system must work after restart and index relocation, with the original build input paths unavailable and no surviving build process.

```bash
/app/run.sh --index-dir /path/to/index --serve
```

After loading, write and flush `{"status":"ready"}` to stdout. Then process one JSON request per stdin line and write and flush one JSON response per stdout line; send diagnostics to stderr. Requests arrive one at a time and contain string `query_id`, numeric `vector` matching the corpus dimension, `filter` in the form `{"all":[tag_id,...]}`, and integer `k` from 0 through 100. Tag IDs are nonnegative integers; scored requests use `k=10`.

Each query has a **15 millisecond** deadline, including request transmission and response JSON decoding. Service loading and evaluator-side request serialization and result checking are excluded.

Return ranked document IDs in this format:

```json
{"query_id":"query-id","results":[{"doc_id":1234}]}
```

Preserve `query_id`; document IDs are integer, zero-based corpus row numbers. Every result must contain all requested tags. Repeated tags have no additional effect, and an empty tag list matches the whole corpus. Return exactly `min(k, matching_document_count)` distinct valid IDs, ordered by ascending squared Euclidean distance, breaking ties by document ID. Equivalent matches at the Top-K distance boundary are accepted. Identical requests must receive identical responses after restart and index relocation.

The score is the fraction of held-out queries returning the complete exact Top-10 within the deadline in both the initial and relocated-index runs. A failed query earns zero; partial Top-K recall earns no credit. Build, index, service-load or required trajectory-audit failure makes the submission score zero.
