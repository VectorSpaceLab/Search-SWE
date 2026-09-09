# Running a task

The shared launcher, `scripts/run_task.sh`, runs tasks with the Codex agent.
Agent credentials, verifier credentials, and optional container proxy settings
are configured locally.

## Prerequisites

With Python 3.12 or newer, install the pinned Harbor version in the environment
you will use to launch tasks:

```bash
python -m pip install -r scripts/requirements-run.txt
```

This installs Harbor and its `python-dotenv` dependency. The tasks use schema
1.4, separate verifier environments, and native Codex configuration.

Prepare Docker, the base images referenced by the task Dockerfiles, and the
CPU/GPU resources required by the task configuration. Restore the task's `data/`
and, where required, `models/` using the [asset download scripts](assets.md).
The launcher checks file presence and size. Use the downloader's `--verify-only`
option for full SHA-256 verification.

## Configure services

From the repository root:

```bash
cp .env.example .env
```

Edit `.env` and fill in:

| Variable | Purpose |
| --- | --- |
| `AGENT_MODEL` | Model used by the coding agent; `--model` overrides it |
| `AGENT_OPENAI_BASE_URL` | Agent API base URL supplied by your provider |
| `AGENT_OPENAI_API_KEY` | Agent API key |
| `VERIFIER_OPENAI_BASE_URL` | Integrity-judge API base URL |
| `VERIFIER_OPENAI_API_KEY` | Integrity-judge API key |
| `TASK_1_1_OPENROUTER_API_KEY` | Required when using task 1-1's permitted task-resource APIs |

The launcher maps the `AGENT_` pair to the agent's `OPENAI_BASE_URL` and
`OPENAI_API_KEY`, and the `VERIFIER_` pair to the verifier's variables of the same
names. They can use different services. To share a service, fill in the same
values in both sections.

Choose a verifier service that supports the Responses API and the judge model
specified in the task's `tests/jailbreak_judge/codex.toml`. `--model` selects
the coding agent; it does not change the task's judge model.

The repository `.env` is loaded automatically if present. `--env-file` selects
another file. Exported shell variables override file values. Values in the file
are literal: shell commands and variable substitutions are not executed. The
launcher does not read `~/.codex/auth.json`. Git ignores `.env`, `.env.*` (except
the template), `*.local.toml`, and `jobs/`.

## Optional proxy

Leave `CONTAINER_PROXY` empty when a container proxy is unnecessary. When needed,
set it to your own proxy URL reachable from inside Docker. The launcher forwards
it as both lowercase and uppercase HTTP/HTTPS proxy variables to the agent and
verifier, with the exclusions in `CONTAINER_NO_PROXY`.

The launcher does not copy the host's ordinary `HTTP_PROXY` or `HTTPS_PROXY`
variables into the container arguments. Host-side proxy settings and Docker
image-pull/build networking are configured separately. A host-only address such
as `127.0.0.1` refers to the container itself when used inside that container.

## Preview and launch

Preview command construction without launching containers or making API calls:

```bash
bash scripts/run_task.sh --task task-1-1 --model gpt-5.6-sol --dry-run
```

The preview prints environment-variable references instead of their values. It
does not validate credentials, assets, hardware, or API availability. After
preparing those prerequisites, launch:

```bash
bash scripts/run_task.sh \
  --task task-1-1 \
  --model gpt-5.6-sol \
  --reasoning-effort xhigh \
  --output jobs/task-1-1-sol
```

The launcher uses Docker, forced image rebuild, setup timeout multiplier 3,
concurrency 1, one attempt, and no retries. It invokes
Harbor with `--yes` after checking required configuration and asset presence.
Harbor writes results below the selected output directory, defaulting to
`jobs/<task-id>/`. Task resource budgets and scoring remain in the task package.

## Custom Codex provider

For a custom provider, keep native Codex settings in a local TOML file and pass
`--codex-config`. For example, save this DeepSeek configuration as
`deepseek.local.toml`:

```toml
model = "deepseek-v4-flash"
model_provider = "deepseek"
model_reasoning_effort = "high"
model_context_window = 1048576

[model_providers.deepseek]
name = "deepseek"
base_url = "https://api.deepseek.com/"
wire_api = "responses"
env_key = "OPENAI_API_KEY"
requires_openai_auth = false
```

Set `AGENT_OPENAI_BASE_URL` to the matching provider URL and
`AGENT_OPENAI_API_KEY` to your own key. Keep the verifier pair configured for its
fixed judge model. Then run:

```bash
bash scripts/run_task.sh \
  --task task-1-1 \
  --model deepseek-v4-flash \
  --codex-config deepseek.local.toml \
  --output jobs/task-1-1-deepseek
```

Clear `AGENT_REASONING_EFFORT` to use the native configuration's effort, or set
`--reasoning-effort` to override it. `--codex-config` paths are relative to your
current directory; `AGENT_CODEX_CONFIG` paths in `.env` are relative to the
repository root. The provider block's URL must agree with your agent endpoint.
