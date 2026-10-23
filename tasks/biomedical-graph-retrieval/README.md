# Biomedical Graph Retrieval

Current run and release status (2026-10-23): [RUN_RESULTS.md](RUN_RESULTS.md). Earlier validation-stage statements are superseded by that dated record.

Author: Cooki-e. Build a reusable search system over the supplied knowledge graph
and return complete sets of internal node IDs. No training or fine-tuning.

The local package includes the corpus, 8 public validation questions and 20
private test questions. Version 0.2.2 retains the original three public examples
and adds five independently verified examples: target-set intersection and
exclusion, distinct support counting, ordinary shortest paths, exclusive-target
pathways, and ordered protein-pair counting. The graph and private split are
unchanged. Public and private query anchors are disjoint; the public set does
not cover every private query structure.

The completed v0.2.1 Codex/OpenRouter `openai/gpt-6-luna`, `max` trial scored
0/20 exact sets with valid execution, no query timeouts and a passing trajectory
audit. That trial used the previous three-example public set; it is not a
v0.2.2 model result. [VALIDATION.md](VALIDATION.md) records the public-data update,
local checks, historical run and finalizer repair separately. Source attribution,
licensing records and construction evidence remain in the authoring workspace;
source dataset names are omitted from this package.

`instruction.md` is the concise agent request; `raw-instruction.md` is its
structured equivalent. Resource and time limits are in the instruction and
`task.toml`. `environment/docs/environment.md` is an exact copy of the shared CPU
environment description. Agents inspect the supplied files to discover their
structure; no separate corpus guide or starter solution is provided.

The verifier runs submitted code as a non-root user, builds once, then runs each
hidden question sequentially with a 30-second deadline. It compares complete ID
sets deterministically. Timeout or wrong answer gives that question zero; failed
build, other execution errors or invalid output invalidates the submission.
A separate trajectory audit gates the final reward.

Only the corpus, public validation and generic resource documents are mounted
into the agent environment. Private questions, labels, grader and audit files
remain verifier-only. No author solutions or screening traces are supplied.

Public inputs are published and pinned to immutable revisions in `assets.json`, with exact sizes and SHA-256 hashes. Unchanged model pins are retained. See [RUN_RESULTS.md](RUN_RESULTS.md) for the current run evidence and publication status. Existing source terms and attribution remain applicable.

```bash
python scripts/download_assets.py --task biomedical-graph-retrieval --verify-only
python -m unittest discover -s tasks/biomedical-graph-retrieval/tests -p 'test_*.py' -v
python scripts/run_task.py --task biomedical-graph-retrieval --agent pi \
  --model deepseek/deepseek-flash --dry-run
```

The last command previews a launch and does not call a model. Completed runtime
evidence, revision coverage and remaining release steps are in [VALIDATION.md](VALIDATION.md).
