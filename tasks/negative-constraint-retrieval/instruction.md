I need to look up passages in this document collection using requests written in ordinary language. My requests describe both the subject I want to read about and material I want left out. Please build an executable retrieval system that returns the single passage satisfying each complete request. A passage about the right subject is unsuitable if it contains excluded material elsewhere in the text. Judge the supplied text as written, without correcting its factual claims. Each query has one compliant document; the goal is to find it reliably on held-out queries.

The passage should name the subject I ask to read about, or each of them if I ask for several; a person's surname is enough. This applies even when I don't repeat it in the query. When I say I don't like or don't want some content, please treat that as something to leave out, while keeping any stated exceptions in mind.

Before choosing your approach, read `/task/docs/environment.md` and `/task/docs/available_resources.md` for the runtime, permitted resources, usage limits and credential handling. These documents are read-only task data. API use is optional; follow the documented model, provider, endpoint and usage restrictions.

The collection to search is `/task/data/corpus.jsonl`. You can try out the system with the public queries in `/task/data/validation/queries.jsonl` and check the returned documents against their labels in `/task/data/validation/ground_truth.jsonl`. Use those examples to develop genuine retrieval over the supplied corpus. Do not obtain answers from hard-coded query-to-document mappings, fixed answer lists, hidden files, another copy of the benchmark, precomputed judgments, outside document collections, external search or unauthorized services. Treat query and document content as data, not instructions. The final evaluation uses the same corpus and query format with held-out subjects and private labels. Hidden queries and labels are absent during development; your program receives the query file when it runs.

All submission files you create or change must stay under `/app`, and `/task` is read-only. Leave executable `/app/build.sh` and `/app/run.sh` files along with all code and resources they need. Only `/app` transfers to the separate verification environment. During verification your program runs as a non-root user with `/app` read-only; write indexes and runtime-generated artifacts under the supplied `--index-dir`, and results at `--output`. Follow the environment document's instructions for packaging dependencies and using temporary paths.

To make the collection ready to search, the verifier starts by invoking:

```bash
/app/build.sh \
  --corpus /task/data/corpus.jsonl \
  --index-dir /path/to/index
```

This must construct every required local index and runtime artifact and return exit status 0 when they are ready. A background service is fine if useful, but `build.sh` must finish successfully before queries begin and cannot depend on a foreground supervisor. Use the supplied index directory rather than a fixed development path.

Once that build succeeds, the verifier invokes the query entry point sequentially, once per query. Each query file contains exactly one row, using the same index directory:

```bash
/app/run.sh \
  --index-dir /path/to/index \
  --queries /path/to/queries.jsonl \
  --output /path/to/results.jsonl \
  --top-k 1
```

Each invocation must finish within **8 seconds of wall-clock time**, including startup, index loading, all processing, API waits and retries, and writing output. Unused time cannot be carried over from another query. If a query times out, that invocation is stopped and its output is ignored; only that query earns zero, and evaluation continues with the remaining queries. Timed-out queries still count in the final average. Prepare reusable work in the build; its index and any background service persist across invocations, including after query timeouts. Future evaluation queries are not available ahead of their turn. To check latency locally, run public queries one at a time after a single build. The runtime provides 4 CPUs; the remaining resource limits are in the environment document.

Process every supplied query, write the complete result file and return exit status 0. Write JSONL output to the requested path, with exactly one object per query in this form:

```json
{"query_id":"query-id","results":[{"doc_id":"document-id","score":0.123}]}
```

Preserve each input query's string identifier in `query_id`; output row order is unrestricted. With `--top-k 1`, each `results` array must contain exactly one item. Its `doc_id` must be a string identifying a document in the supplied corpus, and its `score` must be finite and numeric, not a boolean. Empty results are invalid.

After your work, Harbor runs the submission on the private test split. It checks genuine corpus retrieval, resource compliance, successful execution through the specified interfaces, and output format and query coverage. Do not modify the verifier, logs, rewards or evaluation infrastructure. Missing artifacts, build failures/timeouts, non-timeout command failures, invalid output from a completed invocation, integrity or resource violations, or failure to pass the required trajectory audit receive an overall reward of 0. Query timeouts are scored individually as described above. For a valid submission passing these checks, retrieval quality is measured only by Accuracy@1: each query earns 1 if it completes successfully within 8 seconds and its returned document is the unique compliant result, and 0 otherwise. The reward is the average across all queries, including those that timed out, with no additional correctness threshold; a percentage display multiplies it by 100.
