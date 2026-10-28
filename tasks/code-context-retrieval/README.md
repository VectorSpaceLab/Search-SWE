# Code context retrieval

## Task Metadata

| Field | Value |
| --- | --- |
| Task | `code-context-retrieval` |
| Version | 1.0.0 |
| Authors | Bingyu |
| Primary metric | Mean core-line F1 |
| Compute | 16 CPUs; 32 GiB RAM; 100 GiB storage; 0 GPUs |
| Agent / verifier time limits | 7200 s / 7800 s |
| Dataset | SWE-Explore, original reading-context labels |
| Public queries | 10 |
| Hidden queries | 20 |

Build a reusable search engine that returns the source regions needed to understand and address an issue in a fixed repository snapshot. The target is the original SWE-Explore reading context, including relevant implementation, helpers and tests. It is not exact bug-line localization and does not require generating a patch.

### Data and interface

The shared `data/repos/` directory contains 51,920 complete eligible text files from 30 pinned snapshots across 22 repositories, totaling 324,317,309 bytes. Each snapshot has an anonymous `repo_<id>` root directory; internal relative paths, file bytes and line breaks are preserved. Each query specifies exactly one snapshot to search. Repository names and source-commit mappings are not supplied as runtime metadata; source text and issue content are unchanged and may still identify their projects.

Public validation contains 10 original issues from seven repositories. The verifier holds 20 original issues from 15 different repositories. Repositories do not overlap between splits, and no repository contributes more than three questions to a split. Original issue text is preserved; `read_core_regions` are preserved except for the correction below. The source's outer JSON string encoding is decoded where applicable. Queries identify their target snapshot.

On 2026-10-28, the standalone `include/nlohmann/detail/meta/type_traits.hpp:1–5` reference region was removed from `test-009`. These lines contain only the project banner, version and URL, with no implementation relevant to the unsigned-enum serialization issue. The query retains its other four regions, totaling 201 reference lines. Source files and the 20-query test set are unchanged.

Corpus eligibility matches the screening experiment: regular nonsymlink UTF-8 files up to 1 MiB, nonempty physical line content, no NUL in the first 4096 bytes, excluding `.git`, `node_modules` and `__pycache__`. Original file paths and line breaks remain unchanged. Source-defined Pro file overrides were reproduced without executing setup commands; audited export omissions were restored at the pinned revisions.

The solver supplies executable `/app/build.sh` and `/app/run.sh` with the commands in `instruction.md`. Its `/app` artifacts transfer to a fresh verifier. Public corpus and validation data are separate read-only mounts; only the corpus is mounted in the verifier. Private queries and labels are copied into the verifier image under root-only `/tests`.

## Change Log

| Date | Version | Description |
| --- | --- | --- |
| 2026-10-28 | 1.0.0 | Removed an unrelated five-line header region from test-009 reference labels |

## Difficulty Explanation

### Difficulty evidence

One packaged CPU/API Codex/OpenRouter `openai/gpt-6-luna`, `max` trial produced
mean line F1 and reward **0.17146875932337885** under the labels before the
2026-10-28 correction. The coding agent reached its
7,200-second development limit (`AgentTimeoutError`); the subsequent verifier
completed all 20 queries with valid outputs and no query timeouts. This is a
scored submission after development-budget exhaustion, not an exception-free
agent completion. [VALIDATION.md](VALIDATION.md) records the trial, matching
instruction fingerprint, timings and original evidence locations. No online
trajectory judge is configured for this task.

Author-side screening evaluated the same selected issues with the labels before the 2026-10-28 correction, a common five-region/500-line output budget and a 180-second query limit. Dense retrieval and reranking used local Qwen3 8B models; agents used local Qwen3.5-9B without thinking, at most 25 exploration steps plus a final call. Local GPU pilot latency is not a measurement of the packaged CPU/API environment. Index/model startup was excluded; enhanced-agent timing summed separately measured retrieval and exploration.

| Method | Test mean F1 | Validation mean F1 |
| --- | ---: | ---: |
| Path/symbol heuristic | 0.1058 | 0.1747 |
| BM25 | 0.1050 | 0.1011 |
| Qwen3-Embedding-8B | 0.1936 | 0.3493 |
| BM25 + embedding | 0.1401 | 0.2697 |
| Hybrid + Qwen3-Reranker-8B, 100 candidates | 0.2851 | 0.4195 |
| Multi-turn repository exploration | 0.2298 | 0.2588 |
| Reranked context + one LLM call | 0.1945 | 0.2862 |
| Reranked context + multi-turn tools | 0.2280 | 0.2311 |
| Multi-turn with complete-context prompt | 0.2766 | 0.3939 |
| Previous row + fixed budget repair/file expansion | 0.2370 | 0.6443 |

This is a deliberately selected challenge subset, not a benchmark-wide estimate. Multi-turn exploration did not reliably beat reranking. The validation split is easier, especially for whole-file expansion. Original reading-context labels do not enumerate every useful alternative solution context. Difficulty is supported against the tested local implementations, not every coding agent. The per-question maximum over fixed methods was used only for screening and is not reported as an executable baseline.

## Verification Explanation

### Metric and limits

A result contains up to five source regions and 500 distinct physical lines. Per-query line F1 is `2 * intersection / (predicted_lines + gold_lines)`, matching `(path, line)` in the requested snapshot. Overlaps are deduplicated; ordering has no effect. Every packaged reference set fits the budget and has an attainable oracle score of 1. The reward is the mean over all 20 hidden questions, with no baseline rescaling. Precision and recall are diagnostics.

Invalid or failed query outputs and timeouts score zero for that query. Build failure scores zero overall. A confirmed integrity violation invalidates the submission. Scoring is deterministic; no subjective answer judge is used. The API model allowlist is a task policy; the line scorer alone does not certify model/provider compliance.

The task has 16 CPU cores, 32 GiB RAM, 100 GiB storage, no GPU and a two-hour development budget. Index construction and service readiness have 3,600 seconds. Each query invocation has 180 seconds including API waits and output writing, concurrency one. Both images use the standard CPU image. The resource documents match `agentic-search`; only its documented OpenRouter/Jina retrieval APIs and four Qwen generation models are allowed. Corpus or answer lookup on external sites is not permitted.

See [RUN_RESULTS.md](RUN_RESULTS.md) for recorded run outcomes and judge health, and [VALIDATION.md](VALIDATION.md) for validation evidence.

### Running the task

From the repository root, configure the agent and any task-specific judge credentials using the [evaluation guide](../../docs/evaluation.md), then run:

```bash
python scripts/download_assets.py --task code-context-retrieval
bash scripts/run_task.sh --task code-context-retrieval --model YOUR_AGENT_MODEL
```

## References

### Sources and reproduction

[SWE-Explore paper](https://arxiv.org/abs/2606.07297), [official dataset](https://huggingface.co/datasets/SWE-Explore-Bench/SWE-Explore-Bench), and [official implementation](https://github.com/Qiushao-E/SWE-Explore-Bench).

Dataset revision: `bdb0ae45d7c337d9e1dc3ebfe2a0af6bc7c1fbd9`; release SHA-256: `dc4f114ececd0bfb987361c26ae5e2440456e2cccb36adfccb09ea5385aec202`. Official implementation revision: `5602f031f2d9562d0a805f83402b536e831a5a11`. Issues and base commits were joined by exact IDs to pinned SWE-bench Verified, Multilingual and Pro v1 releases. Attribution and per-snapshot origins are in `LICENSE.data.md`.

The authoring directory is `task_development/code-bug-localization`, adjacent to this Search-SWE checkout. It contains source downloads, the frozen selection, per-query baseline traces, review notes, export scripts, source hashes and author-only runtime fixtures. None is mounted into the solver environment. Reproduce the export with `python task_development/code-bug-localization/package_task.py` from the parent workspace; its input is the already frozen `selection/`.

Run `python scripts/download_assets.py --task code-context-retrieval --verify-only` from this checkout to verify local asset hashes, and `python -m unittest discover -s tasks/code-context-retrieval/tests -p test_contract.py` for scoring regression checks. `VALIDATION.md` records actual runtime checks and remaining validation layers.

Public inputs are published and pinned to immutable revisions in `assets.json`, with exact sizes and SHA-256 hashes. Unchanged model pins are retained. See [RUN_RESULTS.md](RUN_RESULTS.md) for the current run evidence and publication status. Existing source terms and attribution remain applicable.
