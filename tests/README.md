# Repository tests

Install the checkout with `python -m pip install -e .` in Python 3.12+.
Run these commands from the repository root.

## Unit and regression tests

```bash
python -m unittest discover -s tests/unit -p 'test_*.py'
```

[`unit/`](unit/) covers the CLI, credentials, assets, task validation, launcher,
Harbor adapters and network policy using local fixtures and mocks. These tests
run in CI and include Pi trajectory conversion. They do not launch a benchmark
or call live model APIs.

The portable authoring and maintainer skills also test their own workflows:

```bash
python .agents/skills/create-searchswe-task/scripts/test_scaffold_task.py
python .agents/skills/maintain-searchswe-task/scripts/test_maintainer_skill.py
```

## Docker integration checks

[`integration/`](integration/) contains explicit egress lifecycle, transport,
isolation and adapter checks, together with their fixtures. They run separately
from unit-test discovery and require the Docker host, images and configuration
described in the [egress guide](../environments/egress/README.md#verification).
Choose the applicable check and a fresh output directory; inspect its options
with `--help` before execution.

Task-specific verifiers and regression tests live in `tasks/<task-name>/tests/`.
Follow each task's README for its validation commands and runtime requirements.
