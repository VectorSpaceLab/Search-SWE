# Contributing to Search-SWE

Start with the [contribution guide](docs/contributing.md) for task design,
validation, asset publication, and maintainer review. For agent-assisted
authoring, use the [create-searchswe-task skill](.agents/skills/create-searchswe-task/SKILL.md).

New tasks belong at `tasks/<task-name>`. Choose a descriptive name of
at most five lowercase, hyphen-separated words, such as `example-search`.
The `task-` prefix and `all` are reserved. One PR may add multiple tasks; record
actual authors in each package.

Validate each task with grader checks and a configured coding-model trial.
Use the trajectory and evaluation results to identify and correct task-setting
issues, then validate the revised setting and record the final tested version.
If required API keys are missing, the authoring agent should ask the contributor
to configure them locally before running the trial; see the guide for details.

Maintainers review task quality, validation evidence and asset provenance in the
PR. Publish official inputs and pin their merged HF commit before merging the
GitHub contribution. Use a merge commit to preserve original author history.
