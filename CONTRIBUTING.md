# Contributing to Search-SWE

Start with the [contribution guide](docs/contributing.md) for the complete task
workflow, validation commands, asset publication, and maintainer merge checklist.
For agent-assisted authoring, use the
[create-searchswe-task skill](.agents/skills/create-searchswe-task/SKILL.md).

New tasks belong at
`task-submissions/<first-name-slug>/<category>-x-<positive-ordinal>`, **not** in
`tasks/`. Use your chosen ASCII first name, not your GitHub username. One PR may
add multiple tasks, but all must use exactly one contributor namespace.
Maintainers assign each final number and promote every task in the **same PR**,
with a separate pure rename commit followed by finalization. New-task PRs must
use a **merge commit**, never squash or rebase merge.
