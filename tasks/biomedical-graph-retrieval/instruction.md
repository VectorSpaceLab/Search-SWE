Build an executable search system over the supplied knowledge graph. For each question, return the complete set of matching node IDs. Maximize accuracy on held-out questions without training or fine-tuning models. The public examples are illustrative; support new combinations of relationships and conditions.

The corpus is `/task/data/corpus.sqlite`. Public validation questions and answers are in `/task/data/validation/queries.jsonl` and `/task/data/validation/ground_truth.jsonl`.

Read `/task/docs/environment.md` for the installed software and `/task/docs/available_resources.md` for permitted APIs and credential rules. Use only the supplied corpus and permitted services; do not use hard-coded answers, hidden labels, external answer datasets or web search.

You have 16 CPUs, 32 GiB RAM, 100 GiB storage, no GPU, and 120 minutes for implementation and validation. Create all submission files under `/app`; `/task` is read-only. Only `/app` transfers to the separate verifier. There, your program runs as a non-root user with `/app` read-only. Keep dependencies under `/app`, and write indexes, caches and temporary files under the supplied `--index-dir`, honoring `TMPDIR`.

Provide executable `/app/build.sh` and `/app/run.sh`. The verifier builds once:

```bash
/app/build.sh \
  --corpus /task/data/corpus.sqlite \
  --index-dir /path/to/index
```

The build must finish successfully within 1,800 seconds. It may start a background service that remains available for queries.

The verifier then calls `run.sh` sequentially, with one question per input file:

```bash
/app/run.sh \
  --index-dir /path/to/index \
  --queries /path/to/queries.jsonl \
  --output /path/to/results.jsonl
```

Each invocation has a **30-second wall-clock limit** and must exit successfully after writing its result.

Write one JSONL result per question, preserving its identifier and returning distinct integer node IDs:

```json
{"query_id":"query-id","answer_ids":[123,456]}
```

Scoring uses ExactSetAccuracy: a question earns 1 only if the returned set exactly matches the complete answer set; order does not matter. Wrong answers and timeouts earn 0. The displayed score is 100 times the average across all hidden questions.

A failed build, non-timeout execution failure, invalid output or failed compliance audit makes the entire submission score zero.

The integrity review runs independently three times. Its reported value is the arithmetic mean of the three binary decisions. A positive task reward requires all three reviews to accept the submission. A missing, failed or malformed review is an evaluation infrastructure failure.
