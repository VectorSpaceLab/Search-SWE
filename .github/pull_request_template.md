## Summary

Task name(s) and package path(s): `tasks/<task-name>`
Goal, starting system, and CPU/GPU requirements:
Authors and coauthors:

## Validation evidence

List commands, actual results, and task-specific known-good/negative-case
results. List unrun checks and why (data, GPU, credentials, paid APIs).
For task contributions, include the coding-model trial's model/effort, trajectory,
scores and judge health; explain task-setting changes motivated by that feedback
(or why none were needed) and identify the final evaluated revision.

## Contributor checklist

- [ ] New tasks use unique descriptive names of at most five lowercase hyphen-separated words and live at `tasks/<task-name>`.
- [ ] Actual authors in `task.toml`; original author commits preserved.
- [ ] Allow edits from maintainers, or agree on contributor-applied review fixes in this PR.
- [ ] No secrets, downloaded inputs/models, job outputs, or author-only solutions.
- [ ] Static checks and applicable runtime evidence recorded.
- [ ] Provenance, redistribution rights, licenses and immutable development asset SHA documented.

## Maintainer merge checklist

- [ ] Design, verifier isolation, runtime evidence and any validation exceptions reviewed.
- [ ] Names checked against the current base and queued PRs.
- [ ] New official assets published under `tasks/<task-name>/`; previous assets preserved; merged official SHA pinned.
- [ ] Repository docs and inventories updated; checks and merge-ready pass.
- [ ] Merge commit; original contributor history retained.
