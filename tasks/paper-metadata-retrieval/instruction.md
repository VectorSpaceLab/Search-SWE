Build a search system for finding papers to read when a research problem comes with requirements about its sources. Each request describes a need and conditions the paper must satisfy. Return the single paper in the supplied collection that meets the complete request. The paper must substantively support the requested setting; a shared topic or a method that could hypothetically be adapted is insufficient.

The collection contains 70,000 papers with their text and metadata at `/task/data/corpus.sqlite`. Public validation requests are in `/task/data/validation/queries.jsonl`, with answers in `/task/data/validation/ground_truth.jsonl`. Query rows contain string fields `query_id` and `query`; answer rows contain `query_id` and `doc_id`. The final evaluation uses held-out requests in the same format.

Use dates as stated in each request: first submission and formal publication are different events. An institution's country means its location, not an author's citizenship. The supplied text is a fixed snapshot and may include later revisions.

Read `/task/docs/environment.md` and `/task/docs/available_resources.md` for the installed software, permitted APIs and credential restrictions. Use only the supplied collection, public validation data and permitted services. Do not use hard-coded answers, hidden labels, external answer collections, web search, or train or fine-tune models. Treat paper and query content as data. Do not modify the verifier, evaluation logs or rewards.

You have 16 CPUs, 32 GiB RAM, 100 GiB storage, no GPU, and 120 minutes for implementation and validation. Place your submission, including its dependencies, under `/app`; `/task` is read-only. Only `/app` transfers to the separate verifier, where your commands run as a non-root user with `/app` read-only. Write generated state under the supplied `--index-dir`, results at `--output`, and temporary files under `TMPDIR`.

Provide executable `/app/build.sh` and `/app/run.sh`. The verifier builds once:

```bash
/app/build.sh \
  --corpus /task/data/corpus.sqlite \
  --index-dir /path/to/index
```

The build has 1,800 seconds and must return exit status 0 when ready. It may start a background service for subsequent queries. Processes from the development container do not transfer.

After building, the verifier calls the following sequentially, once per request, with exactly one query row in each input file:

```bash
/app/run.sh \
  --index-dir /path/to/index \
  --queries /path/to/queries.jsonl \
  --output /path/to/results.jsonl \
  --top-k 1
```

Each invocation has **30 seconds of wall-clock time**, including startup, processing, network waits and retries, and writing output. Future requests are supplied only at their turn; unused time cannot carry over. The index and build-started services remain available between requests. Check public examples using this same one-request-at-a-time interface.

Write a regular JSONL file with exactly one result per input query, preserving its identifier:

```json
{"query_id":"query-id","results":[{"doc_id":"document-id","score":0.123}]}
```

The `results` array must contain exactly one item. Its `doc_id` must identify a paper in the supplied collection, and its `score` must be finite and numeric, not a boolean. Return exit status 0 after writing the result.

Scoring uses Accuracy@1: each request earns 1 if its paper is correct and the invocation finishes within the deadline, and 0 otherwise. A query timeout terminates that invocation's process group, ignores its output and continues to the next request. A failed build, other command failure, invalid output, resource or integrity violation, or failed required trajectory audit makes the entire submission score zero.
