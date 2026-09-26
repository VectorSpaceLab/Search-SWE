# Running evaluations

This guide documents the complete local evaluation setup. For a first CPU run
with Codex, use the shorter [quick start](quickstart.md).

Run commands from the Search-SWE repository root unless a section says
otherwise.

Search-SWE separates four kinds of configuration:

1. **Coding-agent credentials** run Codex, Pi, or Claude Code.
2. **Verifier credentials** run the private trajectory judge used by most tasks.
3. **Answer-judge credentials** are used only by task 1-3.
4. **Submission-resource credentials** expose task-permitted OpenRouter or Jina
   APIs to the agent's implementation; they are not coding-agent credentials.

Configure only the groups used by the selected row below. On a non-dry run, the
repository launcher enforces required agent and judge groups, while task-resource
keys may remain unset when the submission does not call those optional services.

## Prerequisites

- Python 3.12 or newer.
- Docker with the CPU, memory, storage, and optional GPU capacity declared by
  the selected task.
- Network access to pull the task's versioned base image and restore its fixed
  assets.
- Authorized credentials for every service the selected run uses.

Install the host-side tools in any existing Python 3.12+ environment:

```bash
python -m pip install -r scripts/requirements.txt
```

An isolated venv or Conda environment is recommended if needed, but no
particular environment manager is required. This installs the pinned Harbor
launcher and Hugging Face asset client. Task runtime dependencies remain inside
Docker. Restore only the selected task:

```bash
python scripts/download_assets.py --task TASK_ID
python scripts/download_assets.py --task TASK_ID --verify-only
```

The launcher checks asset presence and size; `--verify-only` performs the full
SHA-256 check. See [assets.md](assets.md) for local caches and offline restore.

Task Dockerfiles pull versioned public images from the
[Search-SWE Docker Hub repository](https://hub.docker.com/r/hanhainebula/search-swe-base):

- `docker.io/hanhainebula/search-swe-base:cpu-py3.12-1.0.0` for CPU tasks;
- `docker.io/hanhainebula/search-swe-base:gpu-cu13.0-py3.12-1.0.0` for GPU tasks.

The matching reproducible build contexts live in [`docker/cpu`](../docker/cpu)
and [`docker/gpu`](../docker/gpu). Normal evaluation does not require rebuilding
the shared images locally.

## Select a task profile

| Task | Hardware | Trajectory judge | Answer judge | Optional submission APIs |
| --- | --- | --- | --- | --- |
| `task-1-1` | CPU | Yes | — | `TASK_1_1_OPENROUTER_API_KEY`, `JINA_API_KEY` |
| `task-1-2` | CPU | Yes | — | — |
| `task-1-3` | CPU | Yes | Yes | `OPENROUTER_API_KEY`, `JINA_API_KEY` |
| `task-1-4` | CPU | Yes | — | `OPENROUTER_API_KEY`, `JINA_API_KEY` |
| `task-2-1` | CPU | Yes | — | — |
| `task-2-2` | 1 NVIDIA GPU | Yes | — | — |
| `task-2-3` | 1 NVIDIA GPU | Yes | — | — |
| `task-2-4` | CPU | — | — | `OPENROUTER_API_KEY`, `JINA_API_KEY` |
| `task-2-5` | CPU | Yes | — | — |

The table identifies credential groups, not the complete resource budget. Read
`tasks/TASK_ID/README.md` and `task.toml` before launching. In particular,
memory, storage, time limits, and asset sizes vary substantially by task.

## Environment-file behavior

The launcher reads `.env` in the repository root by default. Use `--env-file`
for another path. Exported shell variables override file values. Values in the
file are literal: shell commands and `${VARIABLE}` substitutions are not
executed. The launcher does not read `~/.codex/auth.json` or host Claude account
credentials.

Git ignores `.env`, `.env.*` except `.env.example`, `*.local.toml`, and `jobs/`.
Never commit credentials or include them in command-line arguments, logs, task
artifacts, or Docker build layers. On a multi-user Unix host, restrict `.env`
and any custom `--env-file` with `chmod 600`.

## Configure the coding agent

### Codex

Copy `.env.example` and set:

```dotenv
AGENT_MODEL=YOUR_CODEX_MODEL
AGENT_OPENAI_BASE_URL=https://your-agent-endpoint.example/v1
AGENT_OPENAI_API_KEY=YOUR_AGENT_KEY
```

`--model` overrides `AGENT_MODEL`. `--reasoning-effort` overrides the optional
`AGENT_REASONING_EFFORT` environment variable.

For a native Codex TOML, add an absolute path or a path relative to the
repository root:

```dotenv
AGENT_CODEX_CONFIG=provider.local.toml
```

The equivalent CLI option is `--codex-config`; CLI paths are resolved from the
current directory.

### Claude Code with the official Anthropic API

Claude Code is pinned to version 2.1.273 and preinstalled in every task image.
Set a model available to your Anthropic API account and its dedicated
coding-agent key:

```dotenv
AGENT_MODEL=claude-sonnet-4-6
AGENT_ANTHROPIC_API_KEY=YOUR_ANTHROPIC_KEY
```

Then preview or run with the native Harbor adapter:

```bash
bash scripts/run_task.sh \
  --task task-1-1 \
  --agent claude-code \
  --reasoning-effort high \
  --dry-run
```

Claude Code 2.1.273 accepts `low`, `medium`, `high`, `xhigh`, and `max` effort.
Use `AGENT_REASONING_EFFORT` as a local default or `--reasoning-effort` for an
explicit run. The launcher maps `AGENT_ANTHROPIC_API_KEY` to the agent-only
`ANTHROPIC_API_KEY`, permits only `api.anthropic.com` during restricted Agent
phases, and removes inherited Anthropic gateway, OAuth, and Bedrock selectors
before starting Harbor.

The shared launcher intentionally does not support custom Anthropic-compatible
gateways, Claude subscription OAuth, Bedrock, Vertex, ACP, or custom Claude
settings. These modes have different credential, executable-configuration, or
network requirements and must not be enabled by adding host environment
variables.

### Pi native providers

Pi is pinned to version 0.85.1 by the launcher. It currently accepts these
verified provider/model combinations:

| Model | Required variable |
| --- | --- |
| `deepseek/deepseek-flash` | `DEEPSEEK_API_KEY` |
| `zai/glm-5.3-flash` | `ZAI_API_KEY` |

Add only the selected provider key to `.env`, then pass the canonical model ID:

```dotenv
DEEPSEEK_API_KEY=YOUR_DEEPSEEK_KEY
```

```bash
bash scripts/run_task.sh \
  --task task-1-1 \
  --agent pi \
  --model deepseek/deepseek-flash \
  --thinking xhigh \
  --dry-run
```

For Z.AI, set `ZAI_API_KEY` and use `zai/glm-5.3-flash`. The accepted thinking
levels are `off`, `minimal`, `low`, `medium`, `high`, and `xhigh`. Use
`PI_THINKING` as a local default or `--thinking` for an explicit run. Pi's
native provider key does not replace verifier or task-resource credentials.

Pi records native events in `agent/pi.txt` and sessions in `agent/pi/sessions/`.
Search-SWE's adapter converts those events to `agent/trajectory.json` (ATIF);
this is not Pi's native HTML export. It preserves Pi's real `session_id` for
traceability and compatibility with viewers such as ATIF Preview. If an
incomplete log has no session header, the export instead carries a deterministic
content-hash `trajectory_id` and an explanatory note, not a fabricated session ID.
The conversion maps text, reasoning, timestamps and reported token/cost metrics
to standard ATIF fields, retaining raw Pi messages in `extra.pi_message` on
steps and observations. Failed runs are exported before the error is reported.

## Configure judges

All current tasks except `task-2-4` use the trajectory judge. Add:

```dotenv
VERIFIER_OPENAI_BASE_URL=https://api.deepseek.com/
VERIFIER_OPENAI_API_KEY=YOUR_DEEPSEEK_KEY
```

The verifier images pin `harbor-rewardkit==0.2.0` with its Codex CLI 0.147.0
preloaded, and every RewardKit judge is fixed to `deepseek-flash`. `--model`
changes the coding-agent model; it does not change this judge model. The
endpoint is fixed to DeepSeek's official `api.deepseek.com` host by the task
verifier allowlists. A relay on another hostname is rejected rather than
silently broadening verifier egress.

RewardKit 0.2.0 creates a fresh temporary `CODEX_HOME` for each agent judge, so
setting only a host `CODEX_HOME` or `OPENAI_BASE_URL` does not configure that
Codex process. Search-SWE therefore registers a `deepseek-codex` backend that
writes `model_provider = "deepseek"`, `wire_api = "responses"`, the endpoint,
and a `deepseek-flash` model catalog into RewardKit's actual temporary home.
The launcher maps the host `VERIFIER_OPENAI_*` pair to verifier-only
`OPENAI_*` variables. RewardKit moves the key to the child process, where the
provider reads it through `env_key = "DEEPSEEK_API_KEY"`. Search-SWE never
writes the key to TOML or the model catalog and never includes it in a
submission process environment; keep verifier logs private as you would for
any authenticated client. This matches DeepSeek's
[Codex integration](https://api-docs.deepseek.com/zh-cn/quick_start/agent_integrations/codex).

Task 1-3 additionally uses a Chat Completions-compatible answer-equivalence
judge:

```dotenv
ANSWER_JUDGE_MODEL_NAME=YOUR_ANSWER_JUDGE_MODEL
ANSWER_JUDGE_BASE_URL=https://openrouter.ai/api/v1
ANSWER_JUDGE_API_KEY=YOUR_ANSWER_JUDGE_KEY
```

No other current task uses this group. Task 1-3 restricts this judge to the
already permitted `openrouter.ai` host.

## Configure optional submission APIs

Set these only when the selected task and intended submission use the permitted
external resources documented in `tasks/TASK_ID/environment/docs/available_resources.md`.
They do not select the coding-agent or judge model.

Tasks 1-3, 1-4, and 2-4 use the shared variables:

```dotenv
OPENROUTER_API_KEY=YOUR_OPENROUTER_KEY
JINA_API_KEY=YOUR_JINA_KEY
```

Task 1-1 uses a separate OpenRouter credential and the shared Jina credential:

```dotenv
TASK_1_1_OPENROUTER_API_KEY=YOUR_RESTRICTED_OPENROUTER_KEY
JINA_API_KEY=YOUR_JINA_KEY
```

Leaving an optional key empty means the submission cannot use that service.
It does not authorize substituting another provider or model; each task's
resource document is the source of truth.

## GPU tasks

Tasks 2-2 and 2-3 require one NVIDIA GPU. Their images use CUDA 13.0 and require
a compatible NVIDIA driver and Container Toolkit. Both task and verifier
Compose overlays request the real GPU.

Harbor 0.22.0's Docker backend rejects `gpus = 1` during its own preflight and
does not translate that field into the Compose GPU request. The shared launcher
therefore supplies `--override-gpus 0` automatically while leaving the truthful
task metadata and Compose reservations intact. Direct Harbor invocations using
`--env scripts.harbor_environments:PhaseScopedDocker` need the same override
with that Harbor version. Recheck this workaround when upgrading Harbor.

## Runtime network enforcement

Every current task uses a restricted agent or verifier phase, so the launcher
automatically selects the direct gateway and pulls its image if missing. For an
upstream HTTP(S) proxy, configure `EGRESS_CONFIG` using the
[network guide](network-policy.md); proxy mode rejects public phases, including
task-2-3's public agent phase. Keep
`CONTAINER_PROXY` unset: a general proxy would let the proxy choose arbitrary
destinations and would defeat Harbor's hostname policy, so the launcher rejects
it. Configure image-pull and Docker build proxies separately at the Docker
layer; those operations occur before untrusted task execution.

See the [per-task network matrix](network-policy.md) for each environment,
agent, and verifier policy; Harbor field semantics; the exact OpenRouter, Jina,
DeepSeek, Anthropic, and other coding-model hosts; and direct-Harbor guidance.

## Preview and launch

Preview command construction first:

```bash
bash scripts/run_task.sh \
  --task TASK_ID \
  --model YOUR_AGENT_MODEL \
  --dry-run
```

Dry-run output keeps credential references rather than values, but it does not
check credentials, assets, Docker, GPU access, or remote APIs. Then launch into
a fresh jobs root:

```bash
bash scripts/run_task.sh \
  --task TASK_ID \
  --model YOUR_AGENT_MODEL \
  --output jobs/TASK_ID-run-name
```

The launcher uses Docker, forces image builds, runs one attempt with concurrency
one and no retries, and applies a setup-timeout multiplier of three. Repeated
launches below the same output root create separate Harbor jobs; they do not
resume an earlier job automatically. Inspect the resulting reward, verifier
logs, trajectory, and artifacts rather than relying only on the process exit.

## Custom Codex provider

Keep custom native Codex settings in an ignored local TOML. For example:

```toml
model = "YOUR_MODEL_ID"
model_provider = "custom"
model_reasoning_effort = "high"

[model_providers.custom]
name = "Custom provider"
base_url = "https://your-agent-endpoint.example/"
wire_api = "responses"
env_key = "OPENAI_API_KEY"
requires_openai_auth = false
```

Set the `AGENT_OPENAI_*` pair to the matching endpoint and credential, then use
`--codex-config provider.local.toml`. Keep the verifier pair configured for the
task's fixed judge model. Clear `AGENT_REASONING_EFFORT` to use the TOML value,
or pass `--reasoning-effort` to override it.

## Troubleshooting checklist

1. Run with `--dry-run` and confirm the selected task, agent, model, and output.
2. Run `download_assets.py --verify-only` for the selected task.
3. Confirm Docker capacity and, for GPU tasks, `nvidia-smi` plus a GPU-enabled
   test container.
4. Read the launcher's missing-variable error literally; add only the named
   group from this guide.
5. Inspect the Harbor job's agent and verifier logs separately. Agent API,
   verifier API, task-resource API, image build, and submission failures are
   different failure classes.
