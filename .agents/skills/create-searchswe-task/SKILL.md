---
name: create-searchswe-task
description: Create or substantially revise Search-SWE task packages with CPU/GPU environments, fixed inputs, agent instructions, and a separate verifier. Use when contributing tasks, not merely running an existing task.
---

# Create a Search-SWE Task

Deliver a reproducible task whose structured source, natural-language request,
environment, submission interface, and grading agree. Validate the setting
with an actual configured coding-model run as well as grader checks. This skill
contains its authoring guidance and helpers; no outer AGENTS.md, other skill, or historical Harbor workspace is
required. It still operates on a **target Search-SWE checkout**: its tasks,
Docker definitions, and release/download/launch tools are project inputs, not
bundled copies of this skill. Missing tools or incompatible versions are
prerequisites to report, not permission to invent a replacement workflow.

## 1. Establish the design

Read [references/task-authoring.md](references/task-authoring.md). Inspect the
target checkout's status and preserve unrelated changes. Resolve its root
explicitly; do not infer it from where this skill was installed.

Before scaffolding, inspect one or two closest **formal** packages under the
target checkout's `tasks/`. Choose them by engineering mode, evaluation/judge
shape, resources/APIs, hardware and input/artifact layout—not merely by task
number. Record their exact paths and why they are relevant. Treat them as
read-only structural precedents: the current skill, repository validators,
schema and shared-image documentation take priority. Do not copy task-specific
IDs, authors, datasets, thresholds, pins, licenses or access policy without
independently establishing them for the new task. If no close precedent exists,
say so rather than forcing an analogy. See the bounded-reference procedure in
`references/task-authoring.md`.

Record a short design summary before writing the package:

| Decision | What must be known |
| --- | --- |
| Identity | Temporary ID (`task-<1|2>-x-<positive-ordinal>`), one PR-wide first-name slug, actual authors, version |
| Mode | Implementation → `metadata.task_type = "create"`; Optimization → `"optimize"` |
| Goal | What working capability or quality/efficiency improvement is measured |
| Interface | Container input paths, commands, output paths/formats, artifact transfer |
| Evaluation | Metric, public gates, baseline if needed, failure/timeout behavior |
| Inputs | Public/hidden split, actual files, provenance, redistribution rights |
| Resources | CPU/GPU, memory/storage/time, network, permitted APIs/models |
| Precedent | Formal task path(s), matching dimensions, structural patterns reused, intentional differences |

Only these two engineering modes exist. CPU is the default; choose GPU for
actual GPU execution, not merely because model files are involved. Ask for
missing facts that change the design; do not invent labels, licenses, service
access, or quality thresholds. An Optimization task needs a meaningful supplied
starting system/model and comparison criterion, not only a different mode label.

## 2. Create or edit the package

For a new task, run the bundled helper using its **actual installed path**:

```bash
# Set these to real absolute paths; neither depends on the current directory.
SKILL_DIR=/path/to/create-searchswe-task
REPO=/path/to/Search-SWE
python "$SKILL_DIR/scripts/scaffold_task.py" task-1-x-1 \
  --repo-root "$REPO" --submission-first-name Alice --author 'Alice Example' \
  --mode implementation --hardware cpu
```

Category 1 is Implementation (`create`); category 2 is Optimization (`optimize`).
The temporary ID and mode must agree. For optimization:

```bash
python "$SKILL_DIR/scripts/scaffold_task.py" task-2-x-1 \
  --repo-root "$REPO" --submission-first-name Alice --author 'Alice Example' \
  --mode optimization --hardware cpu
```

Hardware is independent of category/mode; use `--hardware gpu` only for GPU work.
New tasks belong in
`task-submissions/<first-name-slug>/<1|2>-x-<positive-ordinal>`, not formal `tasks/` directories.
Use a supplied ASCII first name, not a username; non-Latin names need an explicit
transliteration. Reuse that contributor directory for every task in the PR.
Ordinals are temporary, category-local, positive, and unique in the PR/checkout;
they are not final IDs; never reuse one after promoting its earlier task in the
same PR. If a different contributor with the same first name needs a namespace,
explicitly supply `Alice-2` (then `Alice-3`), including after
checking active PRs; the scaffolder never derives name suffixes from task
collisions. Repeat `--author` for coauthors.
The helper refuses overwrites and symlink roots. Regular mode without
`--submission-first-name` remains compatible for maintainers. Edit an existing
task in place instead; do not delete it to make the helper succeed.

One PR may add multiple tasks, but every task must use exactly one contributor
first-name namespace. Read the bundled
[submission and PR workflow](references/submission-and-pr.md) for branch,
review gates, maintainer handoff and author identity. A maintainer assigns each final ID close to
merge and performs a separate pure rename then finalization for each task in
**the same PR**, using `scripts/promote_task.py`. All tasks must be promoted
before merge. Preserve every promotion commit and original author commit:
**merge commit only**, never squash/rebase. No submission task package enters
final main. Missing workflow tools in an older checkout are a prerequisite to
report, not a reason to invent a formal ID.

The scaffold is **not a finished task**: its verifier always fails, its asset
manifest is empty, data/model mounts are absent, and instructions are writing
prompts. Replace them and review the generated budgets, author, artifact list,
and network settings. The shared image supplies common dependencies; add only
task-specific pinned packages to each Dockerfile. Both Dockerfiles must use
the matching CPU/GPU image, consistent with both Compose files and `gpus`.

## 3. Implement the contract

Follow the detailed rules in `references/task-authoring.md`:

1. Define the submission interface and grader behavior in `raw-instruction.md`.
   Preserve an existing structured instruction there before rewriting. Follow
   [references/instruction-rewrite.md](references/instruction-rewrite.md) to write
   the agent-facing `instruction.md`: a direct user request in connected prose
   describing the task, current data and starting system, available resources,
   constraints, acceptance criteria and optimization objective. Omit
   self-introductions, invented identities and fictional scenes. Preserve every
   condition and exact interface; do not reveal hidden answers. Audit the two
   documents for semantic equivalence before running a model.
2. When adding fixed data/models or external services, read
   [references/assets-and-resources.md](references/assets-and-resources.md).
   Build exact manifests and read-only phase-specific mounts. Keep hidden inputs,
   solutions, and judge credentials out of the agent environment.
3. Write visible environment/resource docs matching what is actually provided.
4. Implement the separate verifier: copy tests into its image, explicitly
   transfer submission artifacts, run untrusted code without grading privileges,
   bound execution, and initialize reward to zero. A separate container does not
   protect a grader from submitted code run as root inside that container.
5. Add author-facing README context and task-local tests, including known-good
   and invalid submissions. Do not change unrelated tasks or scoring policies.

## 4. Validate the task and run a configured model

Read [references/validation.md](references/validation.md) and follow its staged
checks. Stop advancing to expensive runtime tests when inputs, permissions,
hardware, or required configuration are missing. Record the failed command and
diagnosis; retry after a relevant fix, not in an unbounded loop.

After local package, asset and grader checks, follow
[references/model-evaluation.md](references/model-evaluation.md). Run the final
rewritten instruction with the configured coding model and any required judges;
inspect its trajectory, artifacts, grader result and judge health to validate
the task setting. An infrastructure failure does not measure difficulty, and
one low-scoring model run does not establish that a task is impossible.

Local task authoring/validation is the default authorization boundary. It does
not itself authorize commits, pushes, PR creation/comments, publishing data/images, modifying host
network/proxy configuration, or spending on model APIs/GPU jobs. Obtain missing
authorization for those actions only when it is absent from the current
request or prior session. An explicit request to evaluate with a named model
authorizes that scoped run; reuse already-authorized local credentials without
asking again. Ordinary local checks may proceed.

Report the task path, mode/hardware, commands actually executed and their
results, formal reference tasks consulted (or that none was close), intentional
reuse/deviations, the source-to-request equivalence review, known-good/negative-case
evidence, the exact evaluated revision/model/effort, observed scores and judge
health, and every unrun validation layer.
Never equate a scaffold, a dry-run, or a static release check with a solvable
end-to-end task.

When modifying this skill or its scaffolder, run the bundled relocation and
generation checks: `python "$SKILL_DIR/scripts/test_scaffold_task.py"`. They use
temporary directories and do not build images or call APIs.
