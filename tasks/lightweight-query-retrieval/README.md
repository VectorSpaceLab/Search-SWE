# Lightweight query retrieval

## Task Metadata

| Field | Value |
| --- | --- |
| Task | `lightweight-query-retrieval` |
| Version | 1.0.0 |
| Authors | Bingyu |
| Primary metric | Retrieval runtime after a macro nDCG@10 quality gate |
| Compute | 16 CPUs; 32 GiB RAM; 100 GiB storage; 1 GPU |
| Agent / verifier time limits | 21600 s / 3900 s |
| Dataset | BEIR SciFact, NFCorpus and FiQA; author-released LightRetriever examples |
| Hidden queries | 1271 |

Author: Bingyu. Built with Llama.

Build a fast batch retrieval service, subject to a required search-quality
threshold. The agent receives the original Llama-3.2-1B base model and 80,000
original labeled examples. The task does not supply a trained retrieval model,
reference implementation, prebuilt index, or test answers.

### Data and provenance

| Original BEIR collection | Corpus documents | Hidden test queries |
| --- | ---: | ---: |
| SciFact | 5,183 | 300 |
| NFCorpus | 3,633 | 323 |
| FiQA | 57,638 | 648 |
| Total | 66,454 | 1,271 |

Keep original titles, passages, questions, test membership and relevance grades.
Each query names its collection; results are judged against that collection's
complete corpus. The adaptation adds anonymous collection tags and remaps identifiers.
No relevance judgments are generated, and unlabeled documents in other
collections are not added as negatives. No separate public retrieval validation
set is supplied.

Examples come from
[the LightRetriever author release](https://huggingface.co/datasets/lightretriever/lightretriever-finetune-data/tree/840793a0229ead35a9c820e9803092c3f1383e07),
using its original 23-source experiment configuration at
[code revision 9ce35eb](https://github.com/caskcsg/lightretriever/tree/9ce35eb6f3fb96772bcff21fc73a5c973d98f38d).
Allocate exactly 80,000 rows by the authors' source weights using largest
remainders, sample uniformly without replacement within each complete source,
and shuffle with seed 20261018. Preserve original query, positive and negative
passage contents. Empty/invalid rows and normalized exact test-query overlaps
are replaced from the same source without changing its quota. This is a reduced
training input, not the authors' full training run.

The base model is the original
[Meta Llama-3.2-1B](https://huggingface.co/meta-llama/Llama-3.2-1B/tree/4e20de362430cd3b72f300e6b0f18e50e7166e08),
not the Instruct model or the LightRetriever adapter. Its exact official bytes
were acquired from the ModelScope LLM-Research mirror and checked against the
Meta Git/LFS objects. See `THIRD_PARTY_NOTICES.md` and retained model license files.

Source archives:
[SciFact](https://public.ukp.informatik.tu-darmstadt.de/thakur/BEIR/datasets/scifact.zip),
[NFCorpus](https://public.ukp.informatik.tu-darmstadt.de/thakur/BEIR/datasets/nfcorpus.zip),
[FiQA](https://public.ukp.informatik.tu-darmstadt.de/thakur/BEIR/datasets/fiqa.zip).
Source checksums, row-level sampling provenance, audit records and reproducible
preparation scripts are retained in
`../../../task_development/lightretriever`, outside this task package.

## Change Log

| Date | Version | Description |
| --- | --- | --- |
| 2026-10-25 | 1.0.0 | Added initial task |

## Difficulty Explanation

The objective covers complete query processing, including representation and search, across three collections. Faster execution earns credit only after meeting the macro retrieval-quality gate.

## Verification Explanation

### Runtime and scoring

One NVIDIA A100 40GB, 16 CPU cores, 32 GiB RAM, 100 GiB storage, six hours of
development, and no task network/API access. The shared GPU image supplies
Python 3.12 and CUDA 13.0. Index construction has 1,200 seconds; each fresh
service instance has 120 seconds to load. A warm-up uses 24 queries from the
public examples and has 60 seconds. Each complete hidden batch has a 120-second
failure deadline.

The verifier launches candidate code as UID 10001 with a clean environment,
protected hidden inputs and reward files, a read-only submission and built
index, and fresh runtime scratch. Candidate processes and System V IPC objects
are removed between runs. The harness transfers `/app` and the agent execution
trajectory; examples and development processes are unavailable in the separate
verifier. The trajectory is root-only and is inspected alongside the submission
by the required integrity judge.

The verifier permits `openrouter.ai` only for this root-side audit. Candidate
build/service processes receive no judge credentials or proxies and inherit a
seccomp socket filter before dropping privileges, so they remain offline.

For each collection, average original graded nDCG@10 over all its test queries;
take the equal mean across the three collections. Gain is the original qrel
grade, matching `pytrec_eval` / BEIR `ndcg_cut_10`, rather than exponential or
binary conversion. The ideal ranking uses all positive grades up to rank ten.

Let `Q` be the minimum quality across the three runs and `T` their median
timed duration. If `Q < 0.45`, reward is zero. Otherwise the raw retrieval reward is:

```text
retrieval_reward = max(0, 1 - T / 0.8)
```

A score of one is the theoretical upper bound at zero seconds. Every positive
runtime receives less than one; 0.8 seconds or more receives zero. The user
selected this continuous linear rule after reviewing the single-A100 measurements.
The full run records and rationale are in the authoring `calibration-final.json`.

The timed interval includes pipe transfer of the query batch, candidate query
processing and retrieval, response transfer, and response JSON decoding. It
excludes evaluator request serialization, offline build, service loading and
warm-up. Response validation and metric calculation happen after timing.
Malformed output, invalid IDs, missing/duplicate queries, nonfinite or ascending
scores, command failure or exceeded deadlines fail closed to zero.

Final reward equals the raw retrieval reward only when the execution is valid
and the trajectory judge succeeds with a numeric binary pass. Missing or
malformed trajectories, missing/failed audits and nonbinary judge output yield
zero. The grader writes raw results to `report.json`; judge output stays under
`.private/`, and public reward files remain zero until finalization. A confirmed
integrity violation yields zero regardless of retrieval quality or speed.

The rubric distinguishes precomputed benchmark answers from legitimate
corpus-derived indexes, token lookup tables, preprocessing, learned adapters and
parameters trained using the supplied resources. Low quality or slow execution
alone is not an integrity violation.

The judge uses the repository's pinned RewardKit 0.2.0 / DeepSeek V4.1 Flash
wrapper. Configure `VERIFIER_OPENAI_BASE_URL=https://openrouter.ai/api/v1` and
`VERIFIER_OPENAI_API_KEY` locally through the launcher's ignored environment
configuration. The overall verifier budget is 3,900 seconds to include the
audit; the existing 2,300-second retrieval supervisor and all candidate limits
are unchanged.

### Validation and release state

Before the 0.4.0 audit integration, local assets, images, GPU forward/backward, scoring and isolation checks were
executed. A legal implementation trained from the supplied original base and
only supplied examples passed the complete separate verifier with minimum
quality **0.454410**, median **0.860873 seconds**
and reward **0.000000**. See `VALIDATION.md` for the evidence and limits.
The later v0.4.0 verifier run completed its live integrity audit. Macro nDCG@10
was 0.4303102260205993, below the 0.45 gate, and median query-batch time was
0.41057249531149864 seconds. See [RUN_RESULTS.md](RUN_RESULTS.md) for that
measurement and its remaining validation limits, and [VALIDATION.md](VALIDATION.md)
for the separate local checks.

The two derived data assets are published in
[`search-swe/Search-SWE`](https://huggingface.co/datasets/search-swe/Search-SWE/tree/ff16485accd6d258610c158fce45e36b50a47c3f/tasks/lightweight-query-retrieval)
at immutable revision `ff16485accd6d258610c158fce45e36b50a47c3f`.
Their official manifest sizes and SHA-256 hashes match the local inputs.
`assets.json` pins those paths and retains the original upstream model revision;
access to Meta's gated model must also be configured.
Authoring scripts, baselines and trained witness checkpoints are not included
in the agent mounts.

See [RUN_RESULTS.md](RUN_RESULTS.md) for recorded run outcomes and judge health, and [VALIDATION.md](VALIDATION.md) for validation evidence.

### Running the task

From the repository root, configure the agent and any task-specific judge credentials using the [evaluation guide](../../docs/evaluation.md), then run:

```bash
python scripts/download_assets.py --task lightweight-query-retrieval
bash scripts/run_task.sh --task lightweight-query-retrieval --gpu-device 0 --model YOUR_AGENT_MODEL
```

`--gpu-device 0` selects host GPU 0; a full GPU UUID is also accepted. Omit the option to use the default single-GPU allocation. Choose an available device with the task's required capacity. The [GPU guide](../../docs/evaluation.md#gpu-device-selection) explains selection and per-run records.

## References

None.
