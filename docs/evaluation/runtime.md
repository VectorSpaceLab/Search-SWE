# Host setup and native launcher

[Documentation index](../README.md)

Use [the CLI](quickstart.md) for routine evaluations. This reference covers host
requirements, manual credential setup and the single-task backend. Native
commands below run from the checkout root; the CLI handles asset preparation,
configuration and batch scheduling automatically.

## Prerequisites

- Python 3.12+, Git and a compatible Search-SWE package and checkout.
- Native Linux x86_64, local rootful Docker through a Unix socket, and enough
  CPU, RAM and disk for the selected tasks. The gateway uses IPv4 and supports
  Docker without user namespace remapping.
- Network access to pull images, restore inputs and call the configured APIs.
- For GPU tasks, an NVIDIA GPU, a CUDA 13.0-compatible driver and Container Toolkit.
- For bounded-storage tasks, the additional [storage prerequisites](#bounded-task-storage).

Install with `pip install search-swe`, then use `search-swe doctor` for host
checks. Task libraries run in the published CPU/GPU
[base images](../../docker/README.md); ordinary runs pull these images.
See [data and models](assets.md) to plan space for task copies, cache and outputs.

## Select a task

Use `search-swe list` to discover `tasks/*/task.toml`. Read the chosen package:

| File | Details |
| --- | --- |
| `README.md` | Setup, hardware and validation |
| `task.toml` | Resource budgets, artifacts, network policies and environment mappings |
| `environment/docs/available_resources.md` | APIs, models and operations the submission may use |

Configure the variables referenced by that task. [`.env.example`](../../.env.example)
contains common settings; task-specific requirements live with the task.

## Environment-file behavior

The native launcher reads the checkout `.env`, or `--env-file PATH`. Exported
shell variables override file values; explicit flags override their corresponding
settings. File values are literal, including `${VARIABLE}` text. Authentication
comes from these variables rather than host Codex/Claude account files.

Keep credentials in ignored local files with mode `0600`, outside command-line
arguments, logs, artifacts and image layers. `.env`, `.env.*` except `.env.example`,
`*.local.toml` and `jobs/` are Git-ignored. The CLI can configure required keys
with `search-swe configure TASK` or review them with `--edit-credentials`.

## Configure the coding agent

The native backend uses `--openrouter` for OpenRouter; the CLI uses
`--provider openrouter`. These are the supported routes:

| Native options | Model | Host credentials |
| --- | --- | --- |
| `--agent codex --openrouter` | Full OpenRouter ID | `AGENT_OPENROUTER_API_KEY` |
| `--agent claude-code --openrouter` | Full OpenRouter ID with Messages/tool support | `AGENT_OPENROUTER_API_KEY` |
| `--agent pi --openrouter` | Full OpenRouter ID with Chat Completions/tool support | `AGENT_OPENROUTER_API_KEY` |
| `--agent codex` | Direct endpoint's model ID | `AGENT_OPENAI_BASE_URL`, `AGENT_OPENAI_API_KEY` |
| `--agent claude-code` | Official Anthropic model ID | `AGENT_ANTHROPIC_API_KEY` |
| `--agent pi` | Pi `provider/model` ID | Selected provider's key and endpoint settings |

`--model` overrides `AGENT_MODEL`. For Codex/Claude, `--reasoning-effort` overrides
`AGENT_REASONING_EFFORT`; Pi uses `--thinking` or `PI_THINKING`. `default` keeps
the model/harness configuration. See the [agent matrix](agents.md) for model and
authentication scope and [Pi providers](agents.md#pi-api-key-providers) for keys.

### Codex with a direct endpoint

```dotenv
AGENT_MODEL=YOUR_CODEX_MODEL
AGENT_OPENAI_BASE_URL=https://your-agent-endpoint.example/v1
AGENT_OPENAI_API_KEY=YOUR_AGENT_KEY
```

Use `AGENT_CODEX_CONFIG=provider.local.toml` for custom native TOML, or pass
`--codex-config PATH`. Environment paths resolve from the checkout; CLI paths
resolve from the current directory. See [custom configuration](#custom-codex-provider).

### Coding agents through OpenRouter

Set `AGENT_OPENROUTER_API_KEY` and pass `--openrouter --model vendor/model`.
The launcher supplies the API endpoint and coding-model network permission.
Codex uses `https://openrouter.ai/api/v1`; Claude uses
`https://openrouter.ai/api` and preserves the chosen model across its roles.
This mode supplies Codex's provider configuration: omit `--codex-config`;
`AGENT_CODEX_CONFIG` from direct mode is ignored.

New Pi OpenRouter models need catalog metadata resolved before startup.
`--offline-models` uses cached metadata. Coding-agent credentials remain separate
from judge and submission credentials.

### Claude Code with the official Anthropic API

Set `AGENT_ANTHROPIC_API_KEY`, select an Anthropic model with `--model`, and use
`--agent claude-code`. The pinned Claude Code 2.1.309 accepts `low`, `medium`,
`high`, `xhigh` and `max` effort, subject to model support. This route uses the
official API and a key; the launcher removes inherited gateway, OAuth and cloud
selectors. For OpenRouter, use the explicit route above.

### Pi native providers

Find IDs with `search-swe pi-models --provider NAME`, configure that provider's
key/settings, then use `--agent pi --model provider/model`. The pinned Pi 1.4.0
catalog covers API-key providers. `--thinking` accepts `off`, `minimal`, `low`,
`medium`, `high`, `xhigh`, `max` or `default`; the provider applies supported levels.

Pi records events in `agent/pi.txt`, sessions in `agent/pi/sessions/`, and an
ATIF export in `agent/trajectory.json`, including on failed runs. The export
preserves the real session ID when present and raw messages for inspection.

## Configure judges

Trajectory judges use a separate credential pair:

```dotenv
VERIFIER_OPENAI_BASE_URL=https://openrouter.ai/api/v1
VERIFIER_OPENAI_API_KEY=YOUR_OPENROUTER_KEY
```

The verifier pins `harbor-rewardkit==0.2.0`, Codex 0.164.0 and
`deepseek/deepseek-v4.1-flash` through the
[OpenRouter Responses API](https://openrouter.ai/docs/api/api-reference/responses/create-responses).
The endpoint and judge model are fixed; changing the coding-agent `--model`
leaves them unchanged. The backend maps this verifier key to its child process
using `env_key = "OPENROUTER_API_KEY"`; submitted programs receive their own
separate credentials.

Some tasks also declare an answer-equivalence judge. Configure only the variables
referenced by their `task.toml`, for example:

```dotenv
ANSWER_JUDGE_MODEL_NAME=YOUR_ANSWER_JUDGE_MODEL
ANSWER_JUDGE_BASE_URL=https://openrouter.ai/api/v1
ANSWER_JUDGE_API_KEY=YOUR_ANSWER_JUDGE_KEY
```

Use an endpoint permitted by that task's verifier policy. Literal model names
and endpoints in `task.toml` stay fixed; a task may map an answer-judge key to an
existing verifier key. The CLI follows those mappings when prompting.

## Configure submission APIs

The task's resource document defines required and optional submission services.
Common host keys are `OPENROUTER_API_KEY` and `JINA_API_KEY`;
reasoning-query-rewriting uses `REASONING_QUERY_REWRITING_OPENROUTER_API_KEY`.
Leaving an optional key empty disables that service.

**OpenRouter submission allowlists are mandatory:** 47 models for the shared
key and 17 for reasoning-query-rewriting, both excluding
`qwen/qwen3-reranker-8b`. Follow the [key setup guide](submission-models.md).
Coding-agent and judge keys use separate model permissions. Before a native
launch, run `search-swe configure TASK` to check the selected submission keys.

## CPU allocation

The CLI's `--cpu-set` defines a pool for the batch; it allocates disjoint sets
to simultaneous tasks. Native `--cpu-set 0-7` assigns exactly the logical CPU
count declared by the selected task, across its services and both phases,
preserving CPU quotas, RAM limits and mounts. Coordinate native allocations
with other users and keep placement fixed for timing comparisons.

When a task declares an explicit CFS quota matching Harbor's CPU budget at a
100 ms period, the adapter preserves that quota and sets `cpus: 0` in a per-run
Compose copy to disable Harbor's duplicate NanoCPU limit. The CFS quota remains
enforced even on Compose versions that ignore `cpus`. Conflicting budgets or
other periods stop startup; task files and other resource limits remain unchanged.

## GPU tasks

### GPU device selection

GPU tasks request one NVIDIA GPU for both agent and verifier. Select an available
device meeting the task's requirements:

```bash
nvidia-smi --query-gpu=index,uuid,name,memory.used --format=csv
search-swe run code-embedding-finetuning --gpu-devices 2
```

The CLI accepts a pool with `--gpu-devices`; the native launcher takes one host
index or full UUID with `--gpu-device`. It resolves the UUID once and reuses it
for both phases, recording generated configurations under the trial's `gpu/`
directory. Inside the container, the exposed device is CUDA device 0.
Omitting native `--gpu-device` uses the default single-GPU allocation. Use
distinct devices and output directories for concurrent native runs.

### Harbor integration

The launcher handles Harbor 0.22.0's GPU preflight using `--override-gpus 0`
while keeping Compose GPU reservations. Direct Harbor calls need that override
and can pass `--environment-kwarg gpu_device=GPU-<full-UUID>` to
`scripts.evaluation.harbor_environments:PhaseScopedDocker` for selection across
both phases. Recheck this integration when changing Harbor versions.

## Bounded task storage

Tasks with `tools/prepare_task.py` run package-specific preparation automatically after input checks and before Harbor starts the coding agent. The helper receives the selected `--cpu-set` and a temporary `--result-json` path; it writes `{"environment": {"VARIABLE": "value"}}` for the launcher's Compose settings. A failed preparation stops the run. Preview and configuration checks never execute the helper. Packages document their initial preparation cost and cache policy in their README.

Tasks with `tools/prepare_storage.py` use automatic host preparation. In
addition to the host prerequisites, provide root/sudo, `/dev/fuse`, `mkfs.ext4`
and `dpkg-deb` (Ubuntu/Debian packages `e2fsprogs` and `dpkg`). If needed, load
FUSE with `sudo modprobe fuse`. First use downloads verified, pinned FUSE tools.

Each launch creates storage under `jobs/.task-storage/<task-name>/`. Sparse
images grow with use; reserve space for both phases plus inputs, Docker images
and logs. A task's storage limit alone is not the total host disk requirement.
Native launches choose logical CPUs from their allowed affinity; set the task's
`*_CPUSET` for an explicit allocation. Independent launches need disjoint sets.

Only the storage helper uses privilege; Harbor runs as the invoking user and
model keys stay outside the helper. Authenticate sudo before starting or arrange
non-interactive sudo for unattended runs. An explicitly provided `*_STORAGE_ROOT`
uses owner-managed storage and cleanup instead.

Normal exit or interruption checks containers before unmounting. Backing images
remain for inspection. If cleanup cannot confirm that containers are gone, or
the launcher is killed, storage is retained with a recovery command. Stop/remove
that run's containers, follow the printed `prepare_storage.py ... --unmount`
command, then remove images only after mounts are released and results are saved.

## Runtime network enforcement

Restricted phases automatically use the published trusted gateway. For an
upstream proxy or custom DNS, follow the [network guide](network.md). Leave
`CONTAINER_PROXY` unset; the gateway enforces task-specific destinations.
Image pulls and builds use Docker's network configuration, separately from
runtime permissions.

## Preview and launch

For native backend development/debugging, restore and verify assets with the
[asset tools](assets.md#commands), then configure credentials with
`search-swe configure TASK_NAME`. The native launcher checks asset presence and
size; asset restoration supplies the SHA-256 check.

```bash
bash scripts/evaluation/run_task.sh \
  --task TASK_NAME --agent codex --openrouter \
  --model openai/gpt-6-luna --reasoning-effort max \
  --output jobs/TASK_NAME-run-name --dry-run
```

Remove `--dry-run` to launch. It previews command construction without checking
credentials, assets, Docker, GPU access or API connectivity. The launcher builds
images, runs one attempt with concurrency one and no retries, and applies a
setup-timeout multiplier of three. Repeated launches create separate Harbor
jobs rather than resuming; use a fresh output root and inspect scores and
verifier health as well as process status.

## Custom Codex provider

Keep custom native settings in an ignored local TOML:

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

Set the matching `AGENT_OPENAI_*` pair and pass `--codex-config provider.local.toml`.
Use `--reasoning-effort default` to retain the TOML effort, or an explicit level
to override it. Judge configuration remains task-defined.

## Troubleshooting checklist

| Symptom | Next check |
| --- | --- |
| Unexpected task/model/output | Preview with `--dry-run` |
| Missing or corrupt inputs | Follow [asset verification and repair](assets.md#verification-and-resuming) |
| Container or GPU startup failure | Run `search-swe doctor`, inspect Docker logs and test GPU access in a container |
| Missing credentials | Configure the exact variables named in the error |
| API or scoring failure | Inspect agent and verifier logs separately, including judge health |
| Retained mounts or containers | Follow the run's storage recovery message or [gateway cleanup](network.md#isolation-and-recovery) |
