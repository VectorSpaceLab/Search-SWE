# Long-PDF Sentence Evidence Retrieval

## Objective and inputs

Build genuine retrieval that supports brief interpretive questions about one long novel with original sentence evidence. No generated answer. Optimize held-out complete evidence support. Internal parsing, chunking, indexing, and retrieval are open choices within the contract.

- `/task/data/corpus`: one PDF and a question-independent `sentences.jsonl` inventory. Records contain `sentence_id`, `text`, and `pages` (1-based physical PDF indices). Typography/whitespace normalization and fixed unit boundaries cover dialogue and cross-page sentences. Return whole units; do not truncate, merge, paraphrase, or append text. Pages are provenance, not relevance labels.
- `/task/data/validation/queries.jsonl`: 10 public examples, records exactly `query_id` and `query`; opaque IDs, no `target`.
- `/task/data/validation/golden_answers.jsonl`: matching `query_id`, `requirements` list, and `evidence` list of `{sentence_id, sentence}`. These sufficient references are not exhaustive acceptable evidence.
- Twelve hidden queries over the same corpus, with different questions and reference evidence. IDs are independent across splits, ordering unrelated to location. Hidden data is not agent-visible; public validation is not mounted in the verifier.

## Environment and integrity

- Read `/task/docs/environment.md` and `/task/docs/available_resources.md`. Follow their exact model/provider/endpoint allowlists, credential handling, and jailbreak penalties. No implicit unlisted resources. Credentials are runtime-injected, never embedded in artifacts/images.
- 16 CPUs, 16 GiB RAM, 100 GiB storage, no GPU; 120-minute agent allowance including validation/debugging.
- `/task` is read-only; write submission files only under `/app`.
- No hidden labels, hard-coded query-to-location mappings, precomputed query-to-answer mappings/files, external evaluation judgments, or external search/answer services that supply locations/answers. Documented APIs may support genuine retrieval within their policy.

## Executable interface

Provide executable `/app/build.sh` and `/app/run.sh`; optional `/app/src` and `/app/README.md`.

`/app/build.sh --corpus /task/data/corpus --index-dir /app/index`

Create persistent index/runtime artifacts under the passed index directory, start a service, and return 0 only when ready. Service survives repeated queries. Honor supplied paths; verifier paths differ. Agent processes do not transfer to the fresh verifier, so build must recreate the service. Only dependencies in the base image or `/app` are available to unprivileged submission commands.

`/app/run.sh --index-dir /app/index --queries /path/to/queries.jsonl --output /path/to/results.jsonl --top-k 5`

Process every input query, emit exactly one object per query. Verifier calls separately per query. Any compliant internal protocol is allowed. Internal evaluator scheduling uses up to five concurrent calls sharing the index/service; this scheduling detail is omitted from the agent-facing instruction.

## Output

`{"query_id":"opaque-query-id","results":[{"sentence_id":"inventory-id","sentence":"complete inventory text"}]}`

- Exactly these top-level and item fields; preserve input query ID. No page/score/answer fields.
- Zero to five distinct known sentence IDs, not necessarily five. Empty list is valid zero. Order immaterial.
- Text equals the identified unit after Unicode NFKC and whitespace normalization; other punctuation/wording preserved.
- At most 16,000 total submitted sentence characters. Valid JSON, no duplicate keys/query IDs.

## Runtime and grading

- Build: 2,400 seconds. Each query: 30 seconds, measured from its invocation; a timed-out query receives zero. The agent-facing instruction states the per-query limit without a total query-phase budget or concurrency requirement.
- Internal evaluator safeguards: 1,800-second shared query budget, concurrency at most five, with an extra 60 seconds for runner cleanup/result collection. Queuing is excluded from the individual allowance. Whole verifier: 10,800 seconds. These safeguards do not shorten the per-query allowance for the fixed twelve-query workload.
- Check corpus hashes, exact sentence membership and output contract. Then OpenRouter `deepseek/deepseek-v4.1-flash`, effort `high`, temperature 0 judges the entire evidence set. Credentials are verifier-only; this does not extend submission API permissions.
- Binary support: complete explanation/contrast/reversal/qualification = 1, otherwise 0. Topical or scene matching alone fails. Accept alternative evidence; no exact reference-ID requirement. No borrowing missing facts from reference or outside knowledge. Harmless redundant evidence permitted within limits.
- `SentenceEvidenceAccuracy` = mean binary support across all 12 private queries, including failed/invalid/missing/time-out zeros. Isolated failures do not invalidate other queries. Shared build/setup failure prevents all scoring.
- Judge infrastructure/parse errors invalidate measurement and fail closed with final reward 0, separately reported from retrieval mistakes.
- Report `score = 100 * SentenceEvidenceAccuracy`; final reward on 0–1 scale after separate trajectory compliance audit. An unsuccessful audit sets reward to 0.
