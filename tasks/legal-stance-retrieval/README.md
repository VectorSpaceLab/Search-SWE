# Legal stance retrieval

## Task Metadata

| Field | Value |
| --- | --- |
| Task | `legal-stance-retrieval` |
| Version | 1.0.0 |
| Authors | Cooki-e |
| Primary metric | Baseline-normalized mean NDCG@10 |
| Compute | 16 CPUs; 32 GiB RAM; 100 GiB storage; 1 GPU |
| Agent / verifier time limits | 21600 s / 5100 s |
| Hidden queries | 311 |

Given a legal claim and `supported`, `refuted` or `all`, retrieve ten ranked
court-summary document IDs. `all` is the union of both evidence directions;
either direction can be absent. This is retrieval over recorded majority
holdings in a fixed snapshot, not a current-law validity check or verdict
classification. The supplied Qwen3-Embedding-0.6B and public examples are available to the search system. Designated preparation/retrieval APIs remain permitted.

### Frozen data and metric

| Item | Count |
| --- | ---: |
| Full corpus | 3,126 |
| Public example propositions | 5,318 |
| Public query+stance inputs | 10,636 |
| Hidden inputs | 311 |
| Hidden positive query-document pairs | 732 |

All 311 inputs come from the quality-reviewed original official test. There is
no difficulty threshold, authored-query replacement or per-baseline filtering.
The 457 original binary test rows were resolved as 311 retained, 123 excluded
for source/query problems, 21 quarantined and two duplicate propositions removed.
Forty-three Overruled source rows are outside this binary stance task. Retained
claims preserve their original wording. The test stances are 130 supported,
80 refuted and 101 all. The corpus remains byte-identical to the frozen
screening corpus, including original metadata, opaque IDs and shuffled order.

Public training uses the original positive evidence seeds after removing
19 reviewed near-equivalent training propositions and both of their input
variants. Labels have not been exhaustively corrected: cleaning and splitting
these public examples is part of the task. No additional validation set is
removed from these 5,318 propositions. The task exposes no hidden queries or
review artifacts in public mounts. Training/test cases can overlap, while the
reviewed duplicate propositions were removed; this is not case-disjoint testing.

The primary raw metric is mean **binary document-ID NDCG@10**. Relevant documents
have gain 1, other returned IDs gain 0. Ideal DCG uses the first `min(10, |gold|)`
relevant positions. Each query has nonempty qrels. Output order determines rank;
score ties do not require a separate sorting rule. Different document IDs are
scored separately, including records with the same case name. Duplicate IDs in
one answer invalidate the output.

```
B = 0.5610484855098774
reward = max(0, min(1, (mean_ndcg_at_10 - B) / (1 - B)))
```

Normalize after taking the mean. The anchor comes from the unfinetuned local
0.6B serial run rescored on the frozen 311 inputs and reviewed qrels. Its model,
corpus, query, qrels and output fingerprints are in
[tests/data/normalization.json](tests/data/normalization.json). Do not silently
change these inputs or replace B with a rounded value. Minor fresh-run numerical
variation does not change this fixed reward reference.

The reviewed evidence is pooled annotation, not exhaustive expert certification
of every corpus pair. Added positives have explicit author-agent decisions.
Machine-neutral and out-of-pool pairs are not exhaustively adjudicated. Original
training labels remain noisy. The task retains these documented limitations.

## Change Log

| Date | Version | Description |
| --- | --- | --- |
| 2026-10-23 | 1.0.0 | Added initial task |

## Difficulty Explanation

A precedent can be topically relevant while expressing the wrong stance. The system must interpret stance conditions and improve legal retrieval over the fixed baseline within the query budget.

## Verification Explanation

### Execution and resources

The agent receives 16 CPUs, 32 GiB RAM, 100 GiB storage, one NVIDIA GPU and a
6-hour development phase. Both images use the standard GPU base.
`/app/build.sh` receives `--corpus` and `--index-dir`, with a 3,600-second build
budget. `/app/run.sh` receives `--index-dir`, `--queries`, `--output` and
`--top-k 10`. All hidden inputs are passed in **one call with a 20-second
wall-clock deadline**, including command startup/loading, API waits and writing.
There is no per-query or network extension. Build-started services may persist;
agent-container services do not transfer to the separate verifier. Learned
weights and implementation files must be under the transferred `/app`.

The verifier mounts only the fixed corpus, local model and resource docs.
It stages query text only after build completion and runs submission commands
as UID 10001 with a filtered environment. `/app` is read-only to that UID;
the index and result locations are writable. Hidden labels, grading code,
trajectory and reward paths are root-owned. A failed build, failed command,
invalid result or batch timeout gives total zero. No partial timeout credit.
The required DeepSeek trajectory audit remains separate from deterministic
ranking quality and fails closed. No training recipe or minimum weight-change
threshold is imposed by the audit; an honest baseline is a valid zero-improvement
submission. Optional task API credentials are shared `OPENROUTER_API_KEY` and
`JINA_API_KEY`; judge keys are never passed to submission commands.

### Provenance and local assets

The source is [IDIRLab/CaseFacts](https://github.com/idirlab/CaseFacts), downloaded
at repository snapshot `16a4072067c39daa463495e10e3bb029c29beb5b`.
Its downloaded README advertises **CC BY-NC 4.0**; GitHub's license field was
unset. Retain attribution and the noncommercial restriction when distributing
these derived data. The case summaries originate from Oyez, as retained in
original record metadata. See [SOURCES.md](SOURCES.md) for exact input hashes,
transformations and licensing scope. This package is an adaptation, not the
original paper's task, scoring implementation or official benchmark release.
Dataset branding and author-side audit material are kept outside agent docs.

The model is Qwen/Qwen3-Embedding-0.6B (Apache-2.0), pinned to
`97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3`; all local bytes were verified against
the pinned inventory. Runtime corpus/example/model files are restored under
ignored `data/` and `models/`. Hidden test files are copied only into the
verifier image.

Public inputs are published and pinned to immutable revisions in `assets.json`, with exact sizes and SHA-256 hashes. Unchanged model pins are retained. See [RUN_RESULTS.md](RUN_RESULTS.md) for the current run evidence and publication status. Existing source terms and attribution remain applicable.

### Structural precedents and validation

The reviewed `tasks/query-encoder-alignment` and
`tasks/reasoning-query-rewriting` packages at checkout
`46197a43f8cbb364e72b6d63d5db873ae7d2cac8` supply the GPU/model mounts and
build/run search interface respectively. The existing
`tasks/negative-constraint-retrieval` package supplies the already-inspected
unprivileged execution and judge transport pattern; it was an untracked local
package, not claimed as a merged precedent. Intentional differences are a
trainable 0.6B backbone, a whole-suite deadline, no fixed public validation
holdout, and baseline-normalized NDCG. There is no starter or reference solution
inside the task package.

Use [VALIDATION.md](VALIDATION.md) for commands, measured execution, negative-case
checks and outstanding release/model-evaluation layers. The instruction rewrite
keeps fenced build/run examples because the user explicitly requested that format;
this overrides the skill's generic prose-only convention. All source obligations
were checked against the request and grader; see
[instruction-audit.md](instruction-audit.md).

### Instruction revision 0.1.1

The user requested a shorter agent-facing prompt. It now states the provided inputs and model, executable interfaces, whole-batch deadline and mean NDCG@10 objective. Detailed annotation guidance, training-label quality commentary, implementation suggestions and the reward anchor/formula remain author-side. The grader, frozen qrels and reward normalization did not change. General resource and integrity restrictions remain in the linked resource document.

The redundant `model-metadata` directory and its two asset entries were removed. Its files were a model-card copy and a ModelScope `configuration.json`, neither used by the supplied Transformers loader. The actual `config.json`, model weights, tokenizer and SentenceTransformers configuration remain supplied and pinned. The packaging script excludes the removed files so they will not be recreated.

### Public examples — v0.1.2

Public examples are now under `/task/data/examples`, with `queries.jsonl` and `ground_truth.jsonl`. The host directory, Compose mount, asset manifest and packaging output use this name. Public query IDs replace the source `train_` prefix with `example_` in both files; the claim text, stance and relevance maps are unchanged. The agent-facing instruction, resource docs and task description provide the examples and model without suggesting a training method. Original source-split names remain in author provenance and audit records.

See [RUN_RESULTS.md](RUN_RESULTS.md) for recorded run outcomes and judge health, and [VALIDATION.md](VALIDATION.md) for validation evidence.

### Running the task

From the repository root, configure the agent and any task-specific judge credentials using the [evaluation guide](../../docs/evaluation.md), then run:

```bash
python scripts/download_assets.py --task legal-stance-retrieval
bash scripts/run_task.sh --task legal-stance-retrieval --agent codex --openrouter \
  --model openai/gpt-6-luna --reasoning-effort max --gpu-device 0
```

`--gpu-device 0` selects host GPU 0; a full GPU UUID is also accepted. Omit the option to use the default single-GPU allocation. Choose an available device with the task's required capacity. The [GPU guide](../../docs/evaluation.md#gpu-device-selection) explains selection and per-run records.

## References

- [Data, model and method provenance](SOURCES.md).
