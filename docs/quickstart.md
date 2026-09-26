# Quick start

This guide runs one CPU task with the Codex coding agent. It keeps the first
setup small; other tasks, Pi providers, GPU requirements, optional submission
APIs, Claude Code, proxies, and custom Codex providers are covered in the
[full evaluation guide](evaluation.md).

Run every command below from the Search-SWE repository root.

## 1. Install the launcher

Search-SWE requires Python 3.12+, Docker, and enough CPU, memory, and storage
for the selected task. In any existing Python 3.12+ environment, install the
launcher and asset-downloader dependencies directly:

```bash
python -m pip install -r scripts/requirements.txt
```

An isolated venv or Conda environment is recommended if you do not already use
one, but Search-SWE does not require a particular environment manager.
Task-specific Python packages are installed in Docker images, not in this host
environment. Confirm that Docker is available before continuing:

```bash
docker info
```

## 2. Restore one task

Start with `task-1-1`, a CPU task with a small asset bundle. Do not download
every task for a first run:

```bash
python scripts/download_assets.py --task task-1-1
python scripts/download_assets.py --task task-1-1 --verify-only
```

The second command verifies file sizes and SHA-256 checksums. See the
[asset guide](assets.md) for cache, offline, and per-kind options.

## 3. Configure the two services

Copy the complete environment template, then fill only the Codex-agent and
RewardKit-verifier sections used by this walkthrough:

```bash
cp .env.example .env
```

For `task-1-1`, fill in these two credential pairs:

- `AGENT_OPENAI_BASE_URL` and `AGENT_OPENAI_API_KEY` run the coding agent.
- `VERIFIER_OPENAI_BASE_URL=https://api.deepseek.com/` and
  `VERIFIER_OPENAI_API_KEY` run the independent `deepseek-flash` trajectory
  judge through RewardKit 0.2.0.

Set `AGENT_MODEL` in `.env`, or pass `--model` on the command line. The agent
and verifier may use the same DeepSeek account, but they remain separate
configuration groups and only the verifier receives the `VERIFIER_*` values.
`task-1-1` also permits OpenRouter and Jina as submission resources;
their keys are optional and are not needed for an implementation that uses only
the provided corpus and local runtime.

If a proxy is required, set `EGRESS_CONFIG` in `.env` following the
[network guide](network-policy.md); otherwise leave it empty.

The local `.env` is ignored by Git. Do not commit or print credentials. On a
multi-user Unix host, restrict it after adding credentials:

```bash
chmod 600 .env
```

## 4. Preview, then run

First inspect the Harbor command without starting containers or making API
calls:

```bash
bash scripts/run_task.sh --task task-1-1 --dry-run
```

The preview checks command construction only; it does not validate credentials,
assets, Docker, hardware, or service availability. Start a fresh evaluation
after those prerequisites are ready:

```bash
bash scripts/run_task.sh \
  --task task-1-1 \
  --reasoning-effort high \
  --output jobs/task-1-1-codex
```

Omit `--reasoning-effort` when the selected model or provider does not support
it. Results are written below the output directory as Harbor job records.
Inspect the job reward, verifier logs, and transferred artifacts before treating
the run as successful.

## Next steps

- Read the [full evaluation guide](evaluation.md) before selecting another task
  or agent. It documents Codex, Pi, and the pinned Claude Code 2.1.273 launcher,
  and its task matrix lists exactly which additional credentials and hardware
  each task uses.
- Read the selected task's `README.md` and `instruction.md` for its resource
  budget, submission contract, and scoring rules.
- Use the [asset guide](assets.md) to restore only that task's fixed inputs.
