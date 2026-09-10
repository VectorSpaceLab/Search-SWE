# Task-3-1 release package

Task-3-1 evaluates a Python-only learned-sparse retrieval optimization over a
1,000,000-document MS MARCO/SPLADE corpus. The agent receives opaque,
unweighted term IDs and public development data. Hidden queries, qrels, and
reference rankings remain in the separate verifier image.

## Package layout

```text
task-3-1/
├── instruction.md
├── task.toml
├── assets.json
├── data/                         # downloaded corpus/validation data; Git-ignored
├── environment/
│   ├── Dockerfile
│   ├── docker-compose.yaml
│   ├── docs/
│   └── starter/                  # agent-visible corrected starter
└── tests/
    ├── Dockerfile
    ├── docker-compose.yaml
    ├── test.sh
    ├── grader.py
    ├── finalize_reward.py
    ├── jailbreak_judge/
    └── data/                      # verifier-owned hidden inputs
```

## Data download

The corpus and validation files are declared in `assets.json`. The
standard downloader restores them under `data/` and checks both byte size and
SHA-256. The manifest currently has `release_status =
"pending_huggingface_publish"`: the five files still need to be added to the
`search-swe/Search-SWE` dataset, after which every entry's `source.revision`
must be replaced with that upload's 40-character immutable commit hash.

The paths to publish are:

```text
tasks/task-3-1/corpus.jsonl
tasks/task-3-1/validation/queries.jsonl
tasks/task-3-1/validation/qrels.tsv
tasks/task-3-1/validation/stats.json
tasks/task-3-1/validation/reference_top100.jsonl
```

They must retain the sizes and checksums recorded in `assets.json`.

## Harbor launch

After the HF revision is published and the corpus/validation data is downloaded:

```bash
python scripts/download_assets.py --task task-3-1
bash scripts/run_task.sh --task task-3-1 --model <agent-model>
```

The shared launcher discovers this package from `task.toml`, builds the agent
and separate verifier containers, runs one attempt, and passes agent and
verifier API credentials independently. The verifier has public network access
only so the trajectory judge can call its configured OpenAI-compatible
endpoint; the candidate's formal build and search contract remains offline.

## Scoring

The verifier runs the candidate and the verifier-owned corrected, unpruned
starter in the same 1 CPU / 32 GB environment. Reward is binary:

```text
NDCG@10 >= 0.89
qrels Recall@100 >= 0.99
candidate wall time <= 0.30 * corrected-starter wall time
```

All three conditions, output validation, build/run success, and the trajectory
jailbreak judge must pass for reward `1`; any failure gives reward `0`.
