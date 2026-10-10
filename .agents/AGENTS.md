# Search-SWE Task Workflow

This is the contributor workflow entry point. Each skill contains its detailed
guidance. Paths below are relative to the repository root unless expressed as
Markdown links.

## Route the request

- **Create or substantially revise a task:** load
  [create-searchswe-task](skills/create-searchswe-task/SKILL.md) and follow its
  workflow, references, and validation gates. If no native skill loader is
  available, open that `SKILL.md` directly. It can also be invoked independently
  as `$create-searchswe-task`.
- **Review or finalize a task PR as maintainer:** load
  [maintain-searchswe-task](skills/maintain-searchswe-task/SKILL.md), independently
  invocable as `$maintain-searchswe-task`. Default to read-only gh evidence review;
  use its bundled offline HF staging helper only at approved stages.
- **Run an existing task:** use `docs/quickstart.md`; do not scaffold a task.
- **Restore fixed inputs:** use `docs/assets.md` and the existing download tools.
- **Edit project documentation:** keep `README.md` and `README_zh.md` aligned.
  Describe the current contract and workflow directly; keep migration rationale
  in the PR description.
- **Change shared images:** use `docker/README.md`. An ordinary task contribution
  should reuse the CPU/GPU images rather than redesign their shared runtime.

## Coordinate the work

1. Inspect the worktree and agree on the requested deliverable. Preserve other
   contributors' changes. Ask about uncertainties that affect task design or
   authorization, not information already supplied by the user.
2. For task contributions, let the skill drive design → structured source →
   user-request rewrite → grader checks → configured model evaluation → feedback
   and task refinement → revalidation of substantive changes. Preserve
   `raw-instruction.md` and audit all its conditions in the agent-facing
   `instruction.md`. Start from a concrete work need and explain how the
   requested result will be used, then connect the available inputs, constraints,
   acceptance criteria and optimization objective in natural prose. Preserve
   practical context without self-introductions or invented identities; the
   skill defines the rewrite and validation gates.
   Before scaffolding, inspect one or two closest reviewed packages already merged
   into the base branch under `tasks/` as read-only structural precedents, selected
   by engineering objective,
   grading shape, resources and hardware. Apply current repository contracts
   and validators, and independently establish the new task's data, thresholds,
   licenses and access policy.
   A PR may add multiple tasks at `tasks/<task-name>` in its contribution branch.
   Choose a descriptive lowercase name with at most five hyphen-separated words;
   the `task-` prefix and `all` are reserved. Check names against the base and
   active PRs. Follow `CONTRIBUTING.md` and `docs/contributing.md`: record actual
   authors, use `--task <task-name>` for local trials, and finish task review and
   official asset publication before merging with a merge commit. Track completed
   stages, validation evidence and missing inputs or approvals.
   Do not duplicate the skill's specifications in this file.
3. Keep changes within the selected task plus directly necessary integration
   changes. Updating a website, publishing a dataset, pushing images, and opening
   or merging a PR are separate actions, not implied by task creation.
4. Review the resulting diff and validation evidence. Hand off changed paths,
   task objective/hardware, commands actually run, observed results, and blockers.
   Static checks alone are not evidence of a working end-to-end benchmark.
   Include the exact instruction revision, model/effort, trajectory, score and
   judge health from the configured-model validation, plus any resulting task
   changes and evidence for the final revision. Reuse session-authorized runs
   and credentials. If required keys are missing, follow the skill's local
   configuration handoff to the contributor. Do not repeat successful runs just
   because results were moved or a monitoring pane still looks active.

Agents are not guaranteed to auto-load an `AGENTS.md` located under `.agents/`
when editing `tasks/`. Open this entry point explicitly or invoke the skill;
do not assume its directory placement grants repository-wide instruction scope.
