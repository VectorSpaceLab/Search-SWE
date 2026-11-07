# Repository tests

Install the checkout with `pip install -e .` in Python 3.12+.
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

The [harness installation check](integration/harness_install.py) installs selected
CLIs in fresh CPU containers, verifies their real versions, checks cold/warm
cache behavior and confirms task network restrictions are restored. It makes
no model API calls. Choose a fresh output directory and pass `--egress-config`
when your host needs a proxy:

```bash
python tests/integration/harness_install.py --output /tmp/search-swe-harness-check \
  --agents codex claude-code pi gemini-cli antigravity-cli
```

The [bounded log lifecycle check](integration/bounded_logs.py) uses synthetic CLI
executables with real Harbor adapters and an independent verifier. It exercises
Codex, Claude Code, Pi (integrated/native), Gemini and Antigravity using small FUSE
filesystems, including disk-quota exhaustion, protected evidence and ATIF transfer.
It requires root and the formula task's storage prerequisites, and makes no model
or judge API requests. Use `--help` for its fresh output directory and optional
verified FUSE-tool cache.
Antigravity's fixture gives the transcript and run marker identical timestamps.
Add `--agents codex --archive-failure` to check that a sparse oversized log is
retained at the source and stops the trial before the verifier starts.

Task-specific verifiers and regression tests live in `tasks/<task-name>/tests/`.
Follow each task's README for its validation commands and runtime requirements.
