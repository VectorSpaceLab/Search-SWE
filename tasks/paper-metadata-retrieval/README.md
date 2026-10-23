# Paper Metadata Retrieval

## Task Metadata

| Field | Value |
| --- | --- |
| Task | `paper-metadata-retrieval` |
| Version | 1.0.0 |
| Authors | Cooki-e |
| Primary metric | Accuracy@1 |
| Compute | 16 CPUs; 32 GiB RAM; 100 GiB storage; 0 GPUs |
| Agent / verifier time limits | 7200 s / 5400 s |
| Dataset | Fixed full-text paper collection with authored requests |
| Public queries | 3 |
| Hidden queries | 8 |

Author: Cooki-e. Implement reusable Top-1 paper retrieval for natural-language research needs with source conditions. The CPU package provides 70,000 complete papers, 3 public validation requests and 8 verifier-only test requests. No training or fine-tuning.

The public database is `data/corpus.sqlite`, with a single raw `documents` table containing document IDs, bibliographic IDs, titles, abstracts, complete text, metadata JSON and body checksums. It contains no search index, answer annotations, extracted eligibility masks or authoring traces. Source-collection and construction provenance is retained separately in the authoring workspace. Each paper keeps its actual per-record bibliographic and licensing metadata; no blanket redistribution license is asserted for the collection.

## Change Log

| Date | Version | Description |
| --- | --- | --- |
| 2026-10-23 | 1.0.0 | Added initial task |

## Difficulty Explanation

The fixed hidden split consists of the eight requests missed at Top-1 by all 15 original BM25/BGE configurations and all 8 subsequently measured Qwen3 8B configurations. Public validation uses three of the other twelve requests, selected by fewest Qwen Top-1 hits and then lowest mean reciprocal rank. Public and hidden questions and target papers are disjoint; the remaining nine requests are excluded. These are deliberately selected challenge questions, not an unbiased evaluation sample. Source/condition and retrieved-alternative review supports the labels; exhaustive corpus-wide uniqueness and independent human blind review have not been established.

The system must combine research relevance with source conditions over 70,000 full papers. The challenge split contains requests missed by the recorded lexical and neural baselines, with only one returned paper and a per-query deadline.

## Verification Explanation

### Contract and validation

`instruction.md` is the agent request, and `raw-instruction.md` is its structured contract. The public instruction names no source collection and prescribes no retrieval method. Generic CPU and API documents live under `environment/docs/`.

The agent receives only the database, public validation and generic docs. Private questions and labels are copied into the separate verifier image under `/tests/data`; they are never mounted into the agent. At verification, submitted code runs as UID 10001 with `/app` read-only and filtered credentials. Judge keys, verifier files and trajectories remain root-only. Only `/app` and the agent trajectory are transferred. A build has 1,800 seconds; eight sequential single-query invocations each have 30 seconds, including all API time. Query timeouts lose only that query. Other contract failures invalidate the submission. Accuracy@1 is averaged across all eight queries, gated by a separate trajectory audit.

Optional submission resources are OpenRouter/Jina retrieval operations and generation through OpenRouter using exactly `qwen/qwen3.5-9b`. The separate integrity judge uses the same pinned RewardKit/DeepSeek integration as the existing task runtime. The requested CPU, memory, timeouts, network hosts and credential templates are recorded in `task.toml`.

Public assets are published in [`search-swe/Search-SWE`](https://huggingface.co/datasets/search-swe/Search-SWE/tree/8ee1f03ffe70dd7eb57b0bcd8627730fc4232dd3/tasks/paper-metadata-retrieval) at immutable revision `8ee1f03ffe70dd7eb57b0bcd8627730fc4232dd3`. `assets.json` pins their exact paths, sizes and SHA-256 hashes. The [HF publication](https://huggingface.co/datasets/search-swe/Search-SWE/discussions/6) includes source attribution and per-record licensing qualifications; the contributor confirmed additional redistribution authorization. Author-only construction records, baseline results and mechanics fixtures remain outside the task package.

```bash
python scripts/download_assets.py --task paper-metadata-retrieval --verify-only
python -m unittest discover -s tasks/paper-metadata-retrieval/tests -p 'test_*.py' -v
python scripts/check_tasks.py tasks/paper-metadata-retrieval
```

Completed checks and unrun validation layers are recorded in `VALIDATION.md`. Oracle mechanics checks are not coding-agent solutions or live trajectory-judge evidence.

The executable contract is in [instruction.md](instruction.md); [raw-instruction.md](raw-instruction.md) records the structured specification. See [tests/](tests/) for the separate verifier and [task.toml](task.toml) for phase budgets.

See [RUN_RESULTS.md](RUN_RESULTS.md) for recorded run outcomes and judge health, and [VALIDATION.md](VALIDATION.md) for validation evidence.

### Running the task

From the repository root, configure the agent and any task-specific judge credentials using the [evaluation guide](../../docs/evaluation.md), then run:

```bash
python scripts/download_assets.py --task paper-metadata-retrieval
bash scripts/run_task.sh --task paper-metadata-retrieval --model YOUR_AGENT_MODEL
```

## References

None.
