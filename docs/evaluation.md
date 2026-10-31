# Running evaluations

This guide documents the complete local evaluation setup. For a first CPU run
with Codex, use the shorter [quick start](quickstart.md).

The [CLI](cli.md) provides interactive configuration and resource-aware batches:
`search-swe run` opens the wizard, while `search-swe run TASK --yes` uses saved
settings. It restores assets and invokes the single-task backend documented below.
Install the CLI with `python -m pip install search-swe`. For local CLI development,
use `python -m pip install -e .` from the checkout.

Run commands from the Search-SWE repository root unless a section says
otherwise.

Search-SWE separates four kinds of configuration:

1. **Coding-agent credentials** run Codex, Pi, or Claude Code.
2. **Verifier credentials** run the private trajectory judge when configured by the task.
3. **Answer-judge credentials** are needed when the task grades answer equivalence.
4. **Submission-resource credentials** expose task-permitted OpenRouter or Jina
   APIs to the agent's implementation; they are not coding-agent credentials.

Configure the groups declared by the selected task. On a non-dry run, the
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
python -m pip install search-swe
```

An isolated venv or Conda environment is recommended if needed, but no
particular environment manager is required. This installs the pinned Harbor
launcher and Hugging Face asset client. Task runtime dependencies remain inside
Docker. Restore only the selected task:

```bash
python scripts/download_assets.py --task TASK_NAME
python scripts/download_assets.py --task TASK_NAME --verify-only
```

The single-task backend checks asset presence and size; `--verify-only` performs the full
SHA-256 check. See [assets.md](assets.md) for local caches and offline restore.
The CLI performs asset restoration and SHA-256 checking automatically before a batch.

Task Dockerfiles pull versioned public images from the
[Search-SWE Docker Hub repository](https://hub.docker.com/r/hanhainebula/search-swe-base):

- `docker.io/hanhainebula/search-swe-base:cpu-py3.12-1.0.0` for CPU tasks;
- `docker.io/hanhainebula/search-swe-base:gpu-cu13.0-py3.12-1.0.0` for GPU tasks.

The matching reproducible build contexts live in [`docker/cpu`](../docker/cpu)
and [`docker/gpu`](../docker/gpu). Normal evaluation does not require rebuilding
the shared images locally.

## Select a task

Tasks are discovered from `tasks/*/task.toml`; adding a task does not require a
shared task registry or edits to this guide. List available names with
`python scripts/run_task.py --help`. Each package owns its configuration:

- `README.md`: setup, required credential variables, hardware, and validation.
- `task.toml`: resource budgets, artifact transfer, phase-specific network
  policies, and environment-variable mappings.
- `environment/docs/available_resources.md`: APIs/models the submission may use.
- `tests/jailbreak_judge/codex.toml`: the trajectory integrity rubric, when used.

Judge and submission API credentials are task-specific; consult the package
before launching. Configure trajectory-judge credentials when `task.toml` maps
`VERIFIER_OPENAI_*` into `[verifier.env]`.
Add task-specific variables to your ignored `.env` or `--env-file` as documented
by the task. Shared `.env.example` contains common settings and examples, not an
exhaustive inventory. Memory, storage, time limits and asset sizes vary by task.

## Bounded task storage

Tasks with a `tools/prepare_storage.py` helper and `*_STORAGE_ROOT` / `*_CPUSET`
Compose settings use automatic host preparation through `scripts/run_task.sh`.
Use a native Linux x86_64 host with local rootful Docker, without user namespace
remapping, plus root or sudo access. On Ubuntu/Debian, install `e2fsprogs` and
`dpkg` for `mkfs.ext4` and `dpkg-deb`. The host must expose `/dev/fuse`; if the
kernel module is available but unloaded, enable it with `sudo modprobe fuse`.
The helper downloads and verifies its pinned FUSE userspace tools on first use.

The launcher chooses the required number of logical CPUs from its own allowed
affinity. Set the task's `*_CPUSET` variable in `.env` or the shell for a specific
allocation; its CPU IDs and count are checked before startup. Automatic selection
does not reserve idle CPUs across simultaneous evaluations. Assign disjoint sets
when running these tasks concurrently, and preserve the original allocation when
reproducing performance measurements.

Each launch prepares a unique directory under `jobs/.task-storage/<task-name>/`
before Harbor starts. Existing filesystem capacities, resource accounting, task
timers and scoring apply. Allow host disk space for public inputs, images, logs
and both phases' writable filesystems; a task's 64 GiB storage budget is not the
total host disk requirement. The filesystem images are sparse and grow with use.

For an ordinary user, the launcher authenticates sudo once and keeps a dedicated
storage helper alive through teardown. Only that helper is privileged; Harbor
runs as the invoking user. Model API keys are not passed to the helper. For a
background launch, configure non-interactive sudo or authenticate before starting.

On normal exit or a forwarded interrupt, the launcher waits for Harbor and checks
Docker containers before unmounting. Backing images remain available for inspection.
If containers remain, Docker cannot be checked, or the launcher is forcibly killed,
storage is retained and the helper prints its exact recovery command. Stop/remove
only that run's containers before running the displayed `prepare_storage.py ...
--unmount` command. Delete retained images only after their results are no longer
needed and all mounts have been released.

For explicitly managed runs, prepare storage with the task helper as root and
set the task's `*_STORAGE_ROOT` to its absolute path. The launcher uses that
directory; its owner manages unmounting after all associated containers exit.

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

### Codex with a direct endpoint

For the Codex + OpenRouter walkthrough, use the [quick start](quickstart.md)
or the [OpenRouter section](#codex-or-claude-code-through-openrouter) below.
To configure a direct endpoint, copy `.env.example` and set:

```dotenv
AGENT_MODEL=YOUR_CODEX_MODEL
AGENT_OPENAI_BASE_URL=https://your-agent-endpoint.example/v1
AGENT_OPENAI_API_KEY=YOUR_AGENT_KEY
```

`--model` overrides `AGENT_MODEL`. `--reasoning-effort` overrides the optional
`AGENT_REASONING_EFFORT` environment variable.
Use `--reasoning-effort default` to omit the effort override and use the
model/harness configuration. Pi provides the equivalent `--thinking default`.

For a native Codex TOML, add an absolute path or a path relative to the
repository root:

```dotenv
AGENT_CODEX_CONFIG=provider.local.toml
```

The equivalent CLI option is `--codex-config`; CLI paths are resolved from the
current directory.

### Codex or Claude Code through OpenRouter

Set a separate Agent key in `.env`:

```dotenv
AGENT_OPENROUTER_API_KEY=YOUR_AGENT_OPENROUTER_KEY
```

Use a full OpenRouter model slug and select the route explicitly:

```bash
bash scripts/run_task.sh --task reasoning-query-rewriting --agent codex --openrouter \
  --model openai/gpt-6-luna --reasoning-effort max --dry-run
bash scripts/run_task.sh --task reasoning-query-rewriting --agent claude-code --openrouter \
  --model anthropic/claude-opus-5.5 --reasoning-effort xhigh --dry-run
```

Remove `--dry-run` to launch. This mode fixes Codex's Responses base URL to
`https://openrouter.ai/api/v1` and Claude Code's Anthropic base URL to
`https://openrouter.ai/api`. Claude Code accepts only `anthropic/` slugs here.
The launcher permits `openrouter.ai` in restricted Agent phases and keeps the
OpenRouter Agent key separate from `OPENROUTER_API_KEY` for submissions and
`ANSWER_JUDGE_API_KEY` when declared by the task. Verifier configuration is unchanged.
When using Codex, omit `--codex-config`; the launcher supplies the required
native provider configuration and ignores the direct mode's `AGENT_CODEX_CONFIG`.

### Claude Code with the official Anthropic API

Claude Code is pinned to version 2.1.309 and preinstalled in every task image.
Set a model available to your Anthropic API account and its dedicated
coding-agent key:

```dotenv
AGENT_MODEL=claude-sonnet-4-6
AGENT_ANTHROPIC_API_KEY=YOUR_ANTHROPIC_KEY
```

Then preview or run with the native Harbor adapter:

```bash
bash scripts/run_task.sh \
  --task reasoning-query-rewriting \
  --agent claude-code \
  --reasoning-effort high \
  --dry-run
```

Claude Code 2.1.309 accepts `low`, `medium`, `high`, `xhigh`, and `max` effort.
Use `AGENT_REASONING_EFFORT` as a local default or `--reasoning-effort` for an
explicit run. The launcher maps `AGENT_ANTHROPIC_API_KEY` to the agent-only
`ANTHROPIC_API_KEY`, permits only `api.anthropic.com` during restricted Agent
phases, and removes inherited Anthropic gateway, OAuth, and Bedrock selectors
before starting Harbor.

Other custom Anthropic-compatible gateways, Claude subscription OAuth, Bedrock,
Vertex, ACP, and custom Claude settings are not supported. They need different
credentials, executable configuration, or network permissions and must not be
enabled by adding host environment variables.

### Pi native providers

Pi is pinned to version 1.4.0 by the launcher. It currently accepts these
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
  --task reasoning-query-rewriting \
  --agent pi \
  --model deepseek/deepseek-flash \
  --thinking xhigh \
  --dry-run
```

For Z.AI, set `ZAI_API_KEY` and use `zai/glm-5.3-flash`. The accepted thinking
levels are `off`, `minimal`, `low`, `medium`, `high`, `xhigh`, and `max`. Use
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

For a task that uses the trajectory judge, add:

```dotenv
VERIFIER_OPENAI_BASE_URL=https://openrouter.ai/api/v1
VERIFIER_OPENAI_API_KEY=YOUR_OPENROUTER_KEY
```

The verifier images pin `harbor-rewardkit==0.2.0` with Codex CLI 0.164.0
preloaded, and every RewardKit judge is fixed to `deepseek/deepseek-v4.1-flash`. `--model`
changes the coding-agent model; it does not change this judge model. The
trajectory-judge endpoint is `https://openrouter.ai/api/v1`, checked by
the backend and permitted by the verifier allowlists. A relay on another hostname is rejected rather than
silently broadening verifier egress.

The task-local backend selects Codex `0.164.0` through RewardKit 0.2.0's
versioned runtime/cache pin. The verifier image preinstalls that exact version
for both root and task-specific audit users. This integration is checked against
RewardKit 0.2.0; a RewardKit upgrade requires a fresh compatibility check.

RewardKit 0.2.0 creates a fresh temporary `CODEX_HOME` for each agent judge, so
setting only a host `CODEX_HOME` or `OPENAI_BASE_URL` does not configure that
Codex process. Search-SWE therefore registers a `deepseek-codex` backend that
writes `model_provider = "openrouter"`, `wire_api = "responses"`, the endpoint,
and a `deepseek/deepseek-v4.1-flash` model catalog into RewardKit's actual temporary home.
The launcher maps the host `VERIFIER_OPENAI_*` pair to verifier-only
`OPENAI_*` variables. RewardKit moves the key to the child process, where the
provider reads it through `env_key = "OPENROUTER_API_KEY"`. Search-SWE never
writes the key to TOML or the model catalog and never includes it in a
submission process environment; keep verifier logs private as you would for
any authenticated client. The backend uses the
[OpenRouter Responses API](https://openrouter.ai/docs/api/api-reference/responses/create-responses).

A task may additionally declare a Chat Completions-compatible answer-equivalence
judge. Configure the environment variables referenced by its `task.toml`, for example:

```dotenv
ANSWER_JUDGE_MODEL_NAME=YOUR_ANSWER_JUDGE_MODEL
ANSWER_JUDGE_BASE_URL=https://openrouter.ai/api/v1
ANSWER_JUDGE_API_KEY=YOUR_ANSWER_JUDGE_KEY
```

Choose an endpoint allowed by that task's `[verifier].allowed_hosts`. Answer
and trajectory judges are separate credential groups; configure the ones the task declares.
Literal model names and endpoints in `task.toml` remain fixed. A task may map its
answer-judge key to an existing verifier key. The CLI prompts for the actual
referenced variables and keeps these mappings intact.

## CPU allocation

The CLI assigns each simultaneous task a disjoint CPU set. For a native single-task
run, `scripts/run_task.sh --cpu-set 0-7 ...` selects exactly the number of logical
CPUs declared by that task. The generated phase-specific Compose copies apply the
set to all task services, preserving their CPU quotas, RAM limits and mounts.
Use the CLI's `--cpu-set` to specify the available pool for a batch instead.

## Configure optional submission APIs

Set these only when the selected task and intended submission use the permitted
external resources documented in `tasks/TASK_NAME/environment/docs/available_resources.md`.
They do not select the coding-agent or judge model.

For tasks that declare the shared OpenRouter/Jina resources, for example:

```dotenv
OPENROUTER_API_KEY=YOUR_OPENROUTER_KEY
JINA_API_KEY=YOUR_JINA_KEY
```

A task may declare other or namespaced variables. Use its `[environment.env]`
and `[verifier.env]` mappings and task-local documentation; do not add the task
to a shared credential table.

Leaving an optional key empty means the submission cannot use that service.
It does not authorize substituting another provider or model; each task's
resource document is the source of truth.

## GPU tasks

Tasks with `environment.gpus = 1` require one NVIDIA GPU. Their images use CUDA 13.0 and require
a compatible NVIDIA driver and Container Toolkit. Both task and verifier
Compose overlays request the real GPU.

### GPU device selection

Add `--gpu-device` to the usual launcher command to select one host GPU by index
or full UUID. The launcher resolves the device once and uses the same UUID for
the agent and separate verifier:

```bash
nvidia-smi --query-gpu=index,uuid,name,memory.used --format=csv
bash scripts/run_task.sh --task code-embedding-finetuning --agent codex --openrouter \
  --model openai/gpt-6-luna --reasoning-effort max \
  --gpu-device 2 --output jobs/code-embedding-finetuning-gpu2
```

Choose an available device that meets the task's hardware requirements. Selection
is explicit; coordinate concurrent users of the host. For simultaneous runs,
select different GPUs and distinct output directories. Omit the option for the
default single-GPU allocation. CPU tasks accept their usual commands.

Each explicitly selected run stores its generated phase configurations under
`gpu/` in the trial directory. The task files keep their default `count: 1`
reservation; the generated copies replace it with one `device_ids` entry and
retain the original mounts. Run from the local NVIDIA Docker host. Container
CUDA device 0 refers to the single exposed device, regardless of its host index.
`--dry-run` previews the selection without checking GPU availability.

### Harbor integration

Harbor 0.22.0's Docker backend rejects `gpus = 1` during its own preflight and
does not translate that field into the Compose GPU request. The shared launcher
therefore supplies `--override-gpus 0` automatically while leaving the truthful
task metadata and Compose reservations intact. Direct Harbor invocations using
`--env scripts.harbor_environments:PhaseScopedDocker` need the same override
with that Harbor version. Recheck this workaround when upgrading Harbor.
Direct Harbor calls can pass `--environment-kwarg gpu_device=GPU-<full-UUID>` to
`scripts.harbor_environments:PhaseScopedDocker`. Its environment kwargs are
retained when Harbor creates the separate verifier; extra agent-only Compose
overlays are not a replacement for this shared selection.

## Runtime network enforcement

For a restricted agent or verifier phase, the launcher
automatically selects the direct gateway and pulls its image if missing. For an
upstream HTTP(S) proxy, configure `EGRESS_CONFIG` using the
[network guide](network-policy.md); proxy mode rejects public phases. Keep
`CONTAINER_PROXY` unset: a general proxy would let the proxy choose arbitrary
destinations and would defeat Harbor's hostname policy, so the launcher rejects
it. Configure image-pull and Docker build proxies separately at the Docker
layer; those operations occur before untrusted task execution.

See the [network guide](network-policy.md) for phase semantics, coding-model
host selection, and direct-Harbor guidance. The selected task's `task.toml`
defines its actual environment, agent, and verifier policies.

## Preview and launch

Preview command construction first:

```bash
bash scripts/run_task.sh \
  --task TASK_NAME --agent codex --openrouter \
  --model openai/gpt-6-luna --reasoning-effort max \
  --dry-run
```

Dry-run output keeps credential references rather than values, but it does not
check credentials, assets, Docker, GPU access, or remote APIs. Then launch into
a fresh jobs root:

```bash
bash scripts/run_task.sh \
  --task TASK_NAME --agent codex --openrouter \
  --model openai/gpt-6-luna --reasoning-effort max \
  --output jobs/TASK_NAME-run-name
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
