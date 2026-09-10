# Reasoning-intensive Query Rewriting

Build a retrieval system that connects difficult biology questions to supporting documents.

**Task:** `task-1-1` · **Mode:** Implementation · **Metric:** Accuracy@3 with an all-query pass gate

## Overview

A question can describe a biological mechanism without using the terminology
of the document that explains it. This task tests whether a coding agent can
turn that mismatch into a working retrieval pipeline over 57,359 BRIGHT biology
short documents.

The engineering challenge is to connect query interpretation with candidate
retrieval and ranking. A useful rewrite must improve access to evidence without
losing the original information need. The benchmark evaluates the executable
system on held-out questions, rather than judging the wording of its rewrites.

## What This Task Tests

- Translating reasoning-intensive queries into effective retrieval representations.
- Combining retrieval stages while keeping their evidence tied to the supplied corpus.
- Using a very small public validation set without specializing to known answers.
- Packaging indexing and query execution for a fresh verifier environment.

## Task Setup

### Provided Assets

| Asset | Purpose |
| --- | --- |
| `data/corpus.jsonl` | 57,359 documents with opaque IDs and document text |
| `data/validation/` | Three public questions and relevance labels |
| `environment/docs/` | Runtime information and permitted retrieval/generation resources |

The download script restores task-relative `data/`; the container exposes it
read-only under `/task/data`. Three different questions and their labels are
reserved for verification and are not mounted in the agent environment.

### Fixed Components and Allowed Changes

The corpus and submission interface are fixed. Query rewriting, indexing,
candidate selection, and ranking are implementation choices. Selected
OpenRouter and Jina resources are permitted under the
[resource policy](environment/docs/available_resources.md). Connectivity does
not authorize arbitrary external search, answer services, or evaluation data.
The resource document lists exact providers and model IDs.

### Environment and Resource Limits

The CPU Python 3.12 environment provides 16 CPUs, 32 GiB memory, and 100 GiB
storage. The agent has 120 minutes; the Harbor verifier phase has 90 minutes.
Within verification, the current grader allows 1,800 seconds for the submitted
build and 900 seconds for the query run. These submission deadlines are
distinct from Docker image construction.

## Submission Contract

The deliverable is an executable system under `/app`, with `build.sh` preparing
an index and `run.sh` returning three ranked corpus documents per question.
Results carry document IDs and finite scores. The caller supplies the index
location; the verifier runs the submission unprivileged with `/app` read-only.

See [instruction.md](instruction.md) for arguments, result schema, and tie-breaking.
Transferred files must recreate the required runtime: a development-time
background process is not itself a submission.

## Evaluation

### Search Quality

A question is a hit when at least one relevant document appears in its top three.
All three hidden questions must be hits. The verifier reports raw Accuracy@3,
but the task reward is binary rather than partial credit for individual hits.

### Correctness and Resource Gates

Build/run success, complete query coverage, valid corpus IDs, ranking format,
and the execution budgets must all pass.

### Integrity Checks and Final Reward

A separate trajectory judge checks task and resource compliance. Final reward
is `1` only when all hidden cases and the integrity gate pass; otherwise `0`.
The judge assesses the agent's trajectory, not answer quality.

## Running This Task

From the repository root, follow the [launcher guide](../../docs/quickstart.md)
to install the pinned Harbor dependencies, prepare Docker and the task's base
image, and configure the coding-agent credentials. The
[asset guide](../../docs/assets.md) covers downloads, checksums, and cache options.

Configure the verifier's integrity-judge credentials independently of the coding
agent. If the submission uses permitted APIs, task 1-1 uses
`TASK_1_1_OPENROUTER_API_KEY` and the shared `JINA_API_KEY`.

```bash
python scripts/download_assets.py --task task-1-1
bash scripts/run_task.sh --task task-1-1 --model "YOUR_AGENT_MODEL"
```

The shared launcher uses the Codex agent and writes results under `jobs/task-1-1/`.
Replace `YOUR_AGENT_MODEL` with your configured model. Add `--dry-run` to inspect
command construction without starting an evaluation; this does not validate
assets, credentials, or hardware.

## Task Files

| File or directory | What to read it for |
| --- | --- |
| [instruction.md](instruction.md) | Complete agent-facing specification and executable contract |
| [task.toml](task.toml) | Task identity, artifact collection, and phase budgets |
| [assets.json](assets.json) | Fixed asset paths, immutable revisions, and checksums |
| [Environment guide](environment/docs/environment.md) | Installed runtime and task environment |
| [Environment configuration](environment/docker-compose.yaml) | Read-only mounts and hardware requests |
| [Verifier](tests/) | Execution, output validation, and scoring implementation |
| [Resource policy](environment/docs/available_resources.md) | Permitted models, endpoints, and task-resource credentials |
