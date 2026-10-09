---
name: create-searchswe-task
description: Create or substantially revise Search-SWE task packages with CPU/GPU environments, fixed inputs, agent instructions, and a separate verifier. Use when contributing tasks, not merely running an existing task.
---

# Create a Search-SWE Task

Deliver a reproducible task whose structured source, natural-language request,
environment, submission interface, and grading agree. Validate the setting
with an actual configured coding-model run as well as grader checks, and use
the results to refine the setting where needed. This skill contains its authoring
guidance and helpers. It operates on a **target Search-SWE checkout**, which
supplies the task packages, Docker definitions, and release/download/launch
tools. Report missing tools or incompatible versions as prerequisites for the
affected workflow step.

## 1. Establish the design

Read [references/task-authoring.md](references/task-authoring.md). Inspect the
target checkout's status and preserve unrelated changes. Resolve its root
explicitly; do not infer it from where this skill was installed.

Before scaffolding, inspect one or two closest **formal** packages under the
target checkout's `tasks/`. Choose them by engineering objective, evaluation/judge
shape, resources/APIs, hardware and input/artifact layout. Record their exact paths and why they are relevant. Treat them as
read-only structural precedents: the current skill, repository validators,
schema and shared-image documentation take priority. Do not copy task-specific
IDs, authors, datasets, thresholds, pins, licenses or access policy without
independently establishing them for the new task. If no close precedent exists,
say so rather than forcing an analogy. See the bounded-reference procedure in
`references/task-authoring.md`.

Record a short design summary before writing the package:

| Decision | What must be known |
| --- | --- |
| Identity | Descriptive task name (at most five lowercase hyphen-separated words), actual authors, version |
| Goal | What working capability or quality/efficiency improvement is measured |
| Interface | Container input paths, commands, output paths/formats, artifact transfer |
| Evaluation | Metric, public gates, baseline if needed, failure/timeout behavior |
| Inputs | Public/hidden split, actual files, provenance, redistribution rights |
| Resources | CPU/GPU, memory/storage/time, network, permitted APIs/models |
| Precedent | Formal task path(s), matching dimensions, structural patterns reused, intentional differences |

CPU is the default; choose GPU when the agent or verifier executes GPU work. Ask for
missing facts that change the design; do not invent labels, licenses, service
access, or quality thresholds. When improvement over a starting system/model is measured, supply that baseline
and a meaningful comparison criterion.

## 2. Create or edit the package

For a new task, run the bundled helper using its **actual installed path**:

```bash
# Set these to real absolute paths; neither depends on the current directory.
SKILL_DIR=/path/to/create-searchswe-task
REPO=/path/to/Search-SWE
python "$SKILL_DIR/scripts/scaffold_task.py" example-search \
  --repo-root "$REPO" --author 'Alice Example' --hardware cpu
```

Use `--hardware gpu` only for GPU execution. New tasks belong at
`task-submissions/<task-name>`, with `task.name = "search-swe/<task-name>"`.
Names start with an ASCII lowercase letter, contain lowercase letters/digits
and single hyphens, and have at most five words. Use a concise description of
the task; omit the `task-` prefix. `all` is reserved. Check both package roots
and active PRs for collisions. Repeat `--author` for actual coauthors.
The helper refuses overwrites and symlink roots. Its explicit `--formal` option
is for maintainer tooling, not a bypass for new task contributions. Edit an
existing task in place instead of deleting it to make the helper succeed.

One PR may add multiple uniquely named tasks. Read the bundled
[submission and PR workflow](references/submission-and-pr.md). Promotion keeps
the same name: `task-submissions/<task-name>` → `tasks/<task-name>`. Each task
gets its own pure rename commit in **the same PR**, followed by a separate
finalization commit when references, assets or integration need changes. Do not
reuse a submission path in that PR. Preserve original author and promotion
commits: **merge commit only**, never squash/rebase. All tasks must be promoted
before merge; no submission package enters final main.

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

## 4. Validate, test with a model, and refine the setting

Read [references/validation.md](references/validation.md) and follow its staged
checks. Stop advancing to expensive runtime tests when inputs, permissions,
hardware, or required configuration are missing. Record the failed command and
diagnosis; retry after a relevant fix, not in an unbounded loop.

After local package, asset and grader checks, follow
[references/model-evaluation.md](references/model-evaluation.md). Run the final
rewritten instruction with the configured coding model and any required judges;
inspect its trajectory, artifacts, grader result and judge health. Use this
feedback to identify task-setting issues, correct them, and revalidate the
affected checks. Rerun the model when changes affect its task or scoring, within
the authorized budget, and record the final evaluated revision. An infrastructure
failure does not measure difficulty, and one low-scoring model run does not
establish that a task is impossible or justify weakening it.

If required API keys are missing, tell the contributor which variables are
needed, what they are for, and where to configure them locally; never ask for
secret values in chat. Wait for that configuration before the dependent run,
and continue independent checks. The model-evaluation reference details this
handoff and the feedback loop.

Local task authoring/validation is the default authorization boundary. It does
not itself authorize commits, pushes, PR creation/comments, publishing data/images, modifying host
network/proxy configuration, or spending on model APIs/GPU jobs. Obtain missing
authorization for those actions only when it is absent from the current
request or prior session. An explicit request to evaluate with a named model
authorizes that scoped run; reuse already-authorized local credentials without
asking again. Ordinary local checks may proceed.

Report the task path, objective/hardware, commands actually executed and their
results, formal reference tasks consulted (or that none was close), intentional
reuse/deviations, the source-to-request equivalence review, known-good/negative-case
evidence, the exact evaluated revision/model/effort, observed scores and judge
health, feedback-driven task changes (or why none were needed), and every unrun
validation layer.
Never equate a scaffold, a dry-run, or a static release check with a solvable
end-to-end task.

When modifying this skill or its scaffolder, run the bundled relocation and
generation checks: `python "$SKILL_DIR/scripts/test_scaffold_task.py"`. They use
temporary directories and do not build images or call APIs.
