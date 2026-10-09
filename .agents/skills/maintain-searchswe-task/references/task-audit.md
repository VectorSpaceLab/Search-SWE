# Task audit and validation rubric

Record a verdict, concrete evidence and blockers for each relevant row. Review
only the proposed task and directly necessary integration changes; unrelated
workflow/tool modifications need independent scrutiny, not implicit acceptance.

| Area | Evidence required |
| --- | --- |
| Identity/scope | A PR may add multiple tasks, all under exactly one `task-submissions/<first-name-slug>/` namespace. Each `<1|2>-x-<positive-ordinal>` path has the exactly matching canonical ID (for example `task-1-x-1`), with ordinals unique within category in the PR/checkout and never reused after promotion. Reject new tasks added directly under `tasks/`. First name, not username; explicit `alice-2` for a different same-name contributor; actual `task.toml` authors and preserved original commits. No guessed/reserved final IDs. Existing-task revisions stay in place. |
| Repository precedent | For each new task, the contributor names one or two closest formal `tasks/` packages or states that none is close, and explains matching dimensions, structural reuse and intentional differences. Independently inspect the closest analogue by mode, grading/judge shape, resources, hardware and data/artifact layout. Current contracts and validators override legacy examples. Reject unexplained copying of task-specific IDs/authors, datasets or HF pins, thresholds/baselines, allowlists, budgets, licenses/provenance or hidden evaluation design. Merely existing on main is not proof that a pattern remains valid. |
| Instructions | Goal, starting state, input/output schema and absolute paths, submission command/interface, artifacts, public gates/thresholds and constraints match every graded requirement. No secret-only correctness requirement or hidden solution hints. |
| Mode/resources | Only Implementation (`create`) or Optimization (`optimize`); meaningful optimization baseline. CPU default, GPU only for execution. Both Dockerfiles, both Compose reservations and `gpus` agree. Visible tools/API/model docs match injected resources and budgets. Pin dependencies/images; inspect build contexts. |
| Solvability | Real known-good submission through the same separate verifier/artifact-transfer interface, expected vs observed reward and an authorized coding-agent trial. A scaffold's always-zero test, empty manifest, dry-run or static pass is not a working benchmark. No public author-only solution without approval. |
| Grader isolation | Separate verifier; hidden tests/labels/references absent from agent mounts/images. Submitted code actually runs unprivileged with timeout, restricted environment, no grader/reward writes or judge keys. Root in a separate container can still tamper with grading. Reward initializes to zero, numeric finite [0,1], failures propagate, cleanup/logs work. |
| Negative cases | Missing/malformed/duplicate output, timeout, process failure, attempts to read hidden labels or write rewards; no positive fallback on integrity/judge failure. Transfer all declared artifacts; no reliance on live agent sidecars. |
| Heldout validity | Public validation and heldout inputs exercise the same contract without leakage/answer memorization. Public repo `tests/data` is hidden only from the runtime agent, not private. No private answers/secrets in Git or public HF. |
| Network/credentials | Narrow phase-specific allowlists, exact providers/models, no unauthorized calls/spend, runtime-only secret injection, judge keys filtered from submitted processes, no tokens in image/history/logs/artifacts or CLI args. Verify actual backend enforcement. |
| Data/license | Actual bytes match manifest size/SHA-256; immutable 40-hex HF pins; dataset/model/local metadata paths valid. Source provenance, redistribution rights and all license obligations documented, including derived data/models. No guessed license or permanent official temporary-ID paths. |
| Reproducibility | Fresh downloads/hash verification, read-only minimal mounts with missing bind paths failing closed, no host venv/cache dependence, resource/time limits, deterministic grading or justified pinned judge, repeatability and failure diagnoses. |

## Target tools and staged checks

The portable skill deliberately does not bundle Search-SWE's universal validator,
launcher or Harbor runtime. Inspect an explicitly selected **trusted** target
checkout/version providing `scripts/check_submission.py`, `check_release.py`,
`download_assets.py`, `run_task.py` and their dependencies. Missing tools or an
older workflow version stop that layer; do not improvise acceptance commands.
Python 3.12+, PyYAML, python-dotenv and host `scripts/requirements.txt` (Harbor
0.22.0, huggingface_hub 1.x) are target prerequisites. Docker Engine/Compose,
image access and appropriate GPU driver/Container Toolkit are needed for runtime.

After code-execution authorization, from the isolated checkout with trusted tools:

```bash
task_path=task-submissions/alice/1-x-1  # Actual reviewed path; final tasks/<ID> later
python scripts/check_submission.py "$task_path"
python scripts/check_release.py
python -m unittest discover -s scripts/tests -p 'test_*.py'
python scripts/download_assets.py --task-path "$task_path" --dry-run
bash -n "$task_path/tests/test.sh"
git diff --check
# After separate input-download authorization:
python scripts/download_assets.py --task-path "$task_path"
python scripts/download_assets.py --task-path "$task_path" --verify-only
# Preview a configured trial, not evidence of successful runtime:
python scripts/run_task.py --task-path "$task_path" --agent codex --model MODEL_ID --dry-run
```

These commands are target contracts, not permission to execute PR-modified tools.
Inspect tracked and untracked changes. Render both Compose overlays using a
trusted temporary base `main` service/image, then build both contexts only when
authorized. Run known-good and negative verifier cases in disposable environments.
For the documented Harbor 0.22.0 GPU backend, the launcher uses `--override-gpus 0`
while **both** Compose overlays still request the GPU; recheck on version changes.
The launcher does not support `--agent oracle`; a known-good implementation must
be tested separately through the real verifier, in an author-only copy.

Codex trials need `AGENT_OPENAI_BASE_URL`/`AGENT_OPENAI_API_KEY`; judge credentials
are separate `VERIFIER_OPENAI_BASE_URL`/`VERIFIER_OPENAI_API_KEY`, with task APIs
additional. Do not log values. Remove `--dry-run` only after code/runtime/resource
approval and use a fresh `--output jobs/REVIEW-RUN-ID`. Inspect reward, setup errors,
verifier logs and artifacts; record exact commands, head SHA and outcomes. Stop
on missing hardware/auth/data or budget exhaustion; retry only after a relevant
fix. Explicitly report unrun layers, not a blanket 'validated'.

Final readiness additionally requires `python scripts/check_submission.py
--merge-ready` (no submission task.toml), updated inventories including GPU tests,
immutable official asset pins and head-specific required checks. Static CI alone
cannot establish solvability, fair heldout evaluation, licensing or isolation.
