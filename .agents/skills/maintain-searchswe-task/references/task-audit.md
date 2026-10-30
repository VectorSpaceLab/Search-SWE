# Task audit and validation rubric

Record a verdict, concrete evidence and blockers for each relevant row. Review
only the proposed task and directly necessary integration changes; unrelated
workflow/tool modifications need independent scrutiny, not implicit acceptance.

| Area | Evidence required |
| --- | --- |
| Identity/scope | Each new task lives at `tasks/<task-name>/` in the contribution branch, with `task.name = "search-swe/<task-name>"`. Names use at most five lowercase hyphen-separated words, start with a letter, and are unique against the base and active PRs; `task-` and `all` are reserved. A PR may add multiple tasks. Require actual authors and preserve original author commits. Revise existing tasks in place. |
| Repository precedent | For each new task, the contributor names one or two closest reviewed `tasks/` packages already merged into the base branch or states that none is close, and explains matching dimensions, structural reuse and intentional differences. Independently inspect the closest analogue by objective, grading/judge shape, resources, hardware and data/artifact layout. Current contracts and validators override legacy examples. Reject unexplained copying of task-specific IDs/authors, datasets or HF pins, thresholds/baselines, allowlists, budgets, licenses/provenance or hidden evaluation design. Merely existing on main is not proof that a pattern remains valid. |
| Instructions | Compare `raw-instruction.md` with the final `instruction.md`: the agent-facing version starts from a concrete work need and preserves the goal, starting state, input/output schema and paths, executable interface, artifacts, thresholds and constraints. Both match every graded requirement. No secret-only correctness requirement or hidden solution hints. |
| Objective/resources | Clear goal, starting state and measured outcomes. Supply a meaningful baseline when grading improvement. CPU default, GPU only for execution. Both Dockerfiles, both Compose reservations and `gpus` agree. Visible tools/API/model docs match injected resources and budgets. Pin dependencies/images; inspect build contexts. |
| Task README | One task title followed by `Task Metadata`, `Change Log`, `Difficulty Explanation`, `Verification Explanation`, and `References`. Current version matches `task.toml`; new tasks start at `1.0.0` with a dated `Added initial task` entry. Difficulty and validation claims match evidence. References identify existing paper/data/method sources, or `None`. Historical trial versions and fingerprints remain accurate. |
| Solvability | Real known-good submission through the same separate verifier/artifact-transfer interface, expected vs observed reward and an authorized coding-agent trial. A scaffold's always-zero test, empty manifest, dry-run or static pass is not a working benchmark. No public author-only solution without approval. |
| Model feedback | Trajectory, score and judge health inspected; task-setting changes explained, or a reason recorded for retaining the setting. Substantive task/scoring changes have relevant checks and a new model trial within the authorized budget, tied to the final evaluated revision. Missing evidence remains explicit; a valid low score alone is not a reason to weaken the task. |
| Grader isolation | Separate verifier; hidden tests/labels/references absent from agent mounts/images. Submitted code actually runs unprivileged with timeout, restricted environment, no grader/reward writes or judge keys. Root in a separate container can still tamper with grading. Reward initializes to zero, numeric finite [0,1], failures propagate, cleanup/logs work. |
| Negative cases | Missing/malformed/duplicate output, timeout, process failure, attempts to read hidden labels or write rewards; no positive fallback on integrity/judge failure. Transfer all declared artifacts; no reliance on live agent sidecars. |
| Heldout validity | Public validation and heldout inputs exercise the same contract without leakage/answer memorization. Public repo `tests/data` is hidden only from the runtime agent, not private. No private answers/secrets in Git or public HF. |
| Network/credentials | Narrow phase-specific allowlists, exact providers/models, no unauthorized calls/spend, runtime-only secret injection, judge keys filtered from submitted processes, no tokens in image/history/logs/artifacts or CLI args. Verify actual backend enforcement. |
| Data/license | Actual bytes match manifest size/SHA-256; immutable 40-hex HF pins; dataset/model/local metadata paths valid. Public upstream HF datasets may be used directly. Published official inputs may be shared across tasks at their original `tasks/<source-task-name>/...` paths; new uploads use the publishing task's namespace. Document provenance and usage terms, including derived data/models; review redistribution rights for uploaded or mirrored files. No guessed license. |
| Reproducibility | Fresh downloads/hash verification, read-only minimal mounts with missing bind paths failing closed, no host venv/cache dependence, resource/time limits, deterministic grading or justified pinned judge, repeatability and failure diagnoses. |

## Target tools and staged checks

The portable skill deliberately does not bundle Search-SWE's universal validator,
launcher or Harbor runtime. Inspect an explicitly selected **trusted** target
checkout/version providing `scripts/check_tasks.py`, `check_release.py`,
`download_assets.py`, `run_task.py` and their dependencies. Missing tools or an
older workflow version stop that layer; do not improvise acceptance commands.
Python 3.12+ and the host dependencies declared in `pyproject.toml` are target
prerequisites; install with `python -m pip install -e .` from the trusted checkout.
These include Harbor, huggingface_hub, PyYAML and python-dotenv. Docker Engine/Compose,
image access and appropriate GPU driver/Container Toolkit are needed for runtime.

Accept public upstream or official datasets with immutable pins, verified hashes
and documented provenance/usage terms through review and merge-ready stages.
Personal published inputs also need documented redistribution rights. Use the
captured full PR base SHA with `check_tasks.py` so new tasks receive author checks.
Official publication is needed only for files selected for official hosting;
complete it and pin its merged SHA before merging tasks that use those files.
Record any outstanding publication work separately from task-quality findings.

Within the authorized execution scope, from the isolated checkout with trusted tools:

```bash
task_path=tasks/example-search  # Actual package under review
python scripts/check_tasks.py "$task_path" --base FULL_PR_BASE_SHA
python scripts/check_release.py
python -m unittest discover -s scripts/tests -p 'test_*.py'
python scripts/download_assets.py --task "${task_path#tasks/}" --dry-run
bash -n "$task_path/tests/test.sh"
git diff --check
# After separate input-download authorization:
python scripts/download_assets.py --task "${task_path#tasks/}"
python scripts/download_assets.py --task "${task_path#tasks/}" --verify-only
# Preview a configured trial, not evidence of successful runtime:
python scripts/run_task.py --task "${task_path#tasks/}" --agent AGENT_NAME --model MODEL_ID --dry-run
```

These commands are target contracts, not permission to execute PR-modified tools.
Inspect tracked and untracked changes. Render both Compose overlays using a
trusted temporary base `main` service/image, then build both contexts only when
authorized. Run known-good and negative verifier cases in disposable environments.
For the documented Harbor 0.22.0 GPU backend, the launcher uses `--override-gpus 0`
while **both** Compose overlays still request the GPU; recheck on version changes.
For explicit selection, use `--gpu-device <host-index-or-UUID>` with the trusted
launcher. Verify that the generated phase configurations expose the same UUID
and retain task mounts and network controls; package defaults use `count: 1`.
The launcher does not support `--agent oracle`; a known-good implementation must
be tested separately through the real verifier, in an author-only copy.

## Model evidence and local credential setup

Check the contributor's completed trial before scheduling another. Record the
instruction and task revision, selected agent/model/effort, trajectory, raw
metrics, final reward and judge health. Confirm that the job completed and that
required judges returned valid decisions; an authentication or parsing failure
is an invalid measurement. Use this evidence to distinguish solver mistakes from
task-setting defects and review the resulting corrections. Revalidate changed
interfaces, resources or scoring with affected checks and a fresh model trial
within the agreed budget. Retain valid low scores as evidence.

For an authorized maintainer trial, select the agreed Codex, Pi or Claude Code
agent, model and supported effort settings using the trusted checkout's
`docs/evaluation.md`, `.env.example` and task configuration. Check the required
agent, submission API, trajectory-judge and answer-judge credential groups
separately. Reuse configured, authorized keys and check presence without printing
values. If keys are missing, tell the contributor or operator the exact variable
names, their purposes, and how to configure them in an ignored local `.env`, a
supported run-specific env file or the process environment. Ask them to confirm
local configuration without sharing key values in chat, PRs or logs. Continue
independent checks while waiting; start the dependent run after configuration.

Once inputs, credentials, hardware and execution authorization are ready, remove
`--dry-run` and use a fresh `--output jobs/REVIEW-RUN-ID`. Inspect setup errors,
verifier logs and artifacts; record exact commands, head SHA and outcomes. Stop
at the agreed budget or an unmet prerequisite. Retry a terminal infrastructure
failure only after a relevant correction; preserve completed usable trials.

Final readiness additionally requires `python scripts/check_tasks.py
--merge-ready --base FULL_PR_BASE_SHA`, task-local documentation and automatically
discovered GPU/network/judge tests,
verified immutable asset pins and head-specific required checks. Static CI alone
cannot establish solvability, fair heldout evaluation, licensing or isolation.
