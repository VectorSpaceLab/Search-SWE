# Validation and completion evidence

Run commands from the target repository root, using Python 3.12+. For a new
task set `task_path=task-submissions/alice/1-x-1` (your actual first-name slug and
category); after promotion set `task_path=tasks/<final-id>`. These checks use
the checkout's tools; the skill does not bundle a second checker or runtime.

## Target prerequisites (stop if missing)

Verify the explicit checkout contains `scripts/check_submission.py`,
`check_release.py`, `download_assets.py`, `run_task.py`/`run_task.sh`, and their
imports. Use Python 3.12+, host dependencies from `scripts/requirements.txt`
(Harbor 0.22.0 and huggingface_hub 1.x), PyYAML for static Compose parsing, and
python-dotenv for launcher configuration. Install only in an approved host
virtual environment. Do not replace missing target tooling with invented commands.
Docker Engine + Compose are needed for builds/trials, published image access for
pulls, and NVIDIA driver/Container Toolkit for GPU execution. Check provider,
model, credentials, network, disk and runtime budgets before running a trial.
These are target inputs, not portable skill dependencies. `gh` is needed only
for an authorized remote inspection or PR handoff, not local task authoring.

## 1. Inspect the package before execution

- Revisit the recorded formal reference task(s), or the recorded absence of a
  close precedent. Compare only the intended structural patterns and explain
  meaningful deviations; current contracts override legacy behavior. Check that
  no task-specific IDs, data/pins, thresholds, allowlists, licenses or resource
  assumptions were inherited without independent evidence.
- Review `raw-instruction.md` against `instruction.md` using
  [instruction-rewrite.md](instruction-rewrite.md). Account for every source
  condition in the request and trace graded conditions to the verifier.
  Confirm the running agent only receives the rewritten instruction. Public
  limits must not exist only in hidden tests.
- Parse `task.toml` and `assets.json`; verify unique identity, correct mode,
  separate verifier, artifact paths, and all five CPU/GPU configuration points.
- Review all scaffold prose, budgets and empty files. An empty `files` manifest
  is valid only if the task genuinely needs no downloadable fixed inputs.
- Check both build contexts and mounts for hidden-data/solution leakage. Protect
  the grader and reward files from the submitted process; a UID declaration
  without actually using that UID when launching code is insufficient.

```bash
task_path=task-submissions/alice/1-x-1
python scripts/check_submission.py "$task_path" # Before promotion; requires PyYAML
python scripts/check_release.py
python -m unittest discover -s scripts/tests -p 'test_*.py'
python scripts/download_assets.py --task-path "$task_path" --dry-run
bash -n "$task_path/tests/test.sh"
git diff --check
```

Also inspect untracked files with `git status --short` because `git diff` does
not include them. The release checker inspects structure and manifests, not
solvability, full Harbor schema compatibility, or reward correctness.

The current `scripts/tests/test_task_images.py` includes an explicit `GPU_TASKS`
inventory. Adding a GPU task may require updating that expected inventory as a
direct integration change, while retaining image/resource consistency checks.
Do not lower assertions to make a wrongly configured task pass. Download and
launch commands discover formal IDs from `tasks/*/task.toml` automatically;
submissions require explicit `--task-path`. CI review-stage success is not
merge readiness: after same-PR pure rename/finalization, run
`python scripts/check_submission.py --merge-ready` (no submission `task.toml`
may remain). Do not run unreviewed contributor code with secrets; credentialed
runtime testing is separate from unprivileged PR CI.

## 2. Assets, Compose, and images

After restoring authorized inputs with `scripts/download_assets.py`, verify
their SHA-256 checksums with `--verify-only`. The launcher checks only presence
and size, so it does not replace this step. Missing assets are a blocker for
runtime verification, not a reason to create empty files at the mount paths.

Compose files are Harbor overlays. Direct `docker compose config` needs a
temporary base service with an image (this check does not pull that image):

```bash
task_path=task-submissions/alice/1-x-1
(
  set -eu
  base=$(mktemp)
  trap 'rm -f "$base"' EXIT
  printf 'services:\n  main:\n    image: busybox:1.36\n' > "$base"
  for phase in environment tests; do
    docker compose --project-directory "$task_path/$phase" \
      -f "$base" -f "$task_path/$phase/docker-compose.yaml" config -q
  done
)
```

This checks merged configuration, not file availability or actual isolation.
Build both contexts when Docker and the resource/download budget permit:

```bash
docker build -t search-swe-local:alice-agent "$task_path/environment"
docker build -t search-swe-local:alice-verifier "$task_path/tests"
```

GPU images target linux/amd64 with CUDA 13.0 userspace. GPU execution requires
a compatible NVIDIA host driver and Container Toolkit. With the documented
Harbor 0.22.0 Docker backend, `gpus = 1` alone fails preflight. The repository
launcher passes `--override-gpus 0`, while **both Compose overlays still request
the real GPU**. For direct Harbor runs on that backend use the same override;
do not falsify task metadata to work around it. Recheck this behavior if Harbor
changes. CPU tasks do not need the override or NVIDIA reservation.

## 3. Exercise grading and a fresh trial

Test in disposable containers/workspaces, not against host `/app`, `/tests`, or
`/logs`. Run a known-good submission and meaningful negatives: missing output,
malformed/duplicate IDs, command failure, timeout, and attempts to write reward
or read hidden labels. Validate finite scores, logs, process cleanup, and the
actual artifact transfer into the separate verifier. The scaffold's zero-only
test is not a grader and cannot establish solvability.

For Oracle validation, `solution/solve.sh` must contain a real known-good
implementation in an author-only task copy. Do not create a public answer
directory without approval. Alternatively use a separately prepared correct
submission through the same verifier interface. Optimization scores need not
equal one: compare to the agreed baseline/gates and explain the expected result.

The configured coding-model trial is a required validation layer, separate
from known-good and negative-case grading. Follow
[model-evaluation.md](model-evaluation.md) for configuration, a small judge
probe, launch, bounded retries, completion checks and interpretation. If the
required run cannot be executed, hand off the missing evidence explicitly;
do not present static checks or Oracle results as that model run.

## Handoff

Report changed paths, mode, hardware/image selection, input provenance,
formal reference task paths (or no close precedent), structural reuse and
intentional deviations, commands/results for each completed layer, expected
versus observed scores, and unrun layers with their blockers. Distinguish
static, asset, build, grader, known-good and coding-agent E2E results. Do not
label the task ready for release while placeholders or required runtime checks
remain unresolved.
