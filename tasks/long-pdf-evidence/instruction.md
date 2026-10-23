I need to check interpretations of a long novel against its original text. Build an executable retrieval system that returns up to five original sentences which, read together, fully support each question. Return evidence only, without generating an answer.

The PDF and sentence inventory are under `/task/data/corpus`. Public validation questions and reference evidence are in `/task/data/validation/queries.jsonl` and `/task/data/validation/golden_answers.jsonl`.

Read `/task/docs/environment.md` for the runtime and `/task/docs/available_resources.md` for permitted APIs and credential rules. Use only the supplied corpus and permitted services. Do not use hidden labels, hard-coded query-to-location or query-to-answer mappings, external answer datasets, or search services supplying evidence locations or evaluation answers. Never embed credentials in submission files.

You have 16 CPUs, 64 GiB RAM, 100 GiB storage, no GPU, and 120 minutes for implementation and validation. Keep submission files and dependencies under `/app`; `/task` is read-only. Only `/app` transfers to a fresh verifier, where commands run as a non-root user. Development processes do not transfer, and public validation files are unavailable there. Honor all supplied paths, which may differ during verification.

Provide executable `/app/build.sh` and `/app/run.sh`. The verifier builds once:

```bash
/app/build.sh \
  --corpus /task/data/corpus \
  --index-dir /path/to/index
```

The build must finish within **2,400 seconds**, save its index and runtime artifacts under the supplied index directory, and start the retrieval service. Exit successfully only when the service is ready, and keep it available for repeated query calls.

The verifier then invokes:

```bash
/app/run.sh \
  --index-dir /path/to/index \
  --queries /path/to/queries.jsonl \
  --output /path/to/results.jsonl \
  --top-k 5
```

Process every supplied query and exit successfully after writing its result. Verification uses one query per invocation, with a **30-second wall-clock limit**. A timed-out query receives zero.

Write one JSONL result per query, preserving its identifier and using exactly these fields:

```json
{"query_id":"query-id","results":[{"sentence_id":"sentence-id","sentence":"complete original sentence"}]}
```

Return zero to five distinct, complete units from the supplied `sentences.jsonl`, with matching IDs and text. Only Unicode NFKC and whitespace differences are tolerated; do not truncate, combine, paraphrase or append text. The combined sentence text for a query must not exceed **16,000 characters**. Use valid JSON without duplicate keys or query IDs. Evidence order does not matter.

Scoring uses `SentenceEvidenceAccuracy`: the fraction of held-out questions fully supported by the returned evidence. Alternative correct evidence is accepted; matching the public reference IDs is not required. Incomplete, empty, invalid, failed or timed-out results earn zero for that query. A failed build, failed shared initialization or unsuccessful compliance audit makes the final reward zero. The displayed score is 100 times the accuracy; final reward is on the 0–1 scale.
