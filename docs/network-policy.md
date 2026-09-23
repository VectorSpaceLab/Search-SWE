# Runtime network policy

Search-SWE uses Harbor 0.22.0's native `network_mode` and `allowed_hosts`
fields. `allowed_hosts` contains hostnames only—not URLs, ports, or paths—and is
valid only with `network_mode = "allowlist"`. Docker enforcement uses Harbor's
egress-control sidecar. If the Docker host cannot enforce the requested policy,
Harbor rejects the run instead of silently granting public access.

## Current task matrix

`model host` below means exactly one coding-model hostname selected by the
launcher: the hostname in `AGENT_OPENAI_BASE_URL` for Codex,
`api.deepseek.com` for Pi + DeepSeek, `api.z.ai` for Pi + Z.AI, or the fixed
`api.anthropic.com` host for Claude Code. The launcher passes it through
Harbor's `--allow-agent-host`, which augments only the `agent.run()` phase.
Codex 0.147.0, Pi 0.85.1, and Claude Code 2.1.273 are preinstalled in every
agent image, so agent setup does not need package-registry or general internet
access.

| Task | Task/runtime requirement | `[environment]` baseline | Effective agent phase | Verifier phase |
| --- | --- | --- | --- | --- |
| `task-1-1` | OpenRouter/Jina resources only | allowlist: `openrouter.ai`, `api.jina.ai` | task hosts + model host | task hosts + `api.deepseek.com` |
| `task-1-2` | Fully local vector retrieval | no network | model host only | `api.deepseek.com` only |
| `task-1-3` | OpenRouter/Jina RAG resources | allowlist: `openrouter.ai`, `api.jina.ai` | task hosts + model host | task hosts + `api.deepseek.com`; OpenRouter also serves the answer judge |
| `task-1-4` | OpenRouter/Jina resources only | allowlist: `openrouter.ai`, `api.jina.ai` | task hosts + model host | task hosts + `api.deepseek.com` |
| `task-2-1` | Fixed local reranker only | no network | model host only | `api.deepseek.com` only |
| `task-2-2` | Explicitly offline training | no network | model host only | `api.deepseek.com` only |
| `task-2-3` |  OpenRouter/Jina resources only | allowlist: `openrouter.ai`, `api.jina.ai` | task hosts + model host | task hosts + `api.deepseek.com` |
| `task-2-4` | OpenRouter/Jina resources only | allowlist: `openrouter.ai`, `api.jina.ai` | task hosts + model host | task hosts only; no model judge |
| `task-2-5` | Formal build/search is offline | no network | model host only | `api.deepseek.com` only |

The verifier-only DeepSeek hostname does not expose its credential to submitted
commands. Task 1-3 similarly removes both judge credential groups before
running submission code. Submission API keys are injected only for tasks whose
resource policy permits those APIs.

## Direct Harbor runs

The repository launcher derives and supplies the coding-model host. When
invoking Harbor directly on a non-public task, add the matching hostname:

```bash
harbor run --path tasks/TASK_ID --env docker \
  --agent scripts.harbor_agents:PreinstalledCodex --model MODEL_ID \
  --ak version=0.147.0 \
  --allow-agent-host MODEL_API_HOST
```

For the supported official-Anthropic Claude Code mode, use the pinned wrapper,
an environment reference rather than a literal secret, and the fixed host:

```bash
harbor run --path tasks/TASK_ID --env docker \
  --agent scripts.harbor_agents:PreinstalledClaudeCode \
  --model ANTHROPIC_MODEL_ID \
  --ak version=2.1.273 \
  --ae 'ANTHROPIC_API_KEY=${AGENT_ANTHROPIC_API_KEY}' \
  --allow-agent-host api.anthropic.com
```

The repository launcher additionally removes inherited gateway, OAuth, and
Bedrock selectors. Reproduce that sanitization when bypassing it; custom
Anthropic endpoints and alternate Claude authentication modes are not part of
the supported configuration.

Do not use `--allow-environment-host` for a coding-model endpoint: that changes
the environment baseline rather than only the agent phase. Do not add package
registries, source-code hosts, wildcard domains, or a general HTTP proxy to a
task allowlist. A general proxy reduces destination filtering to the proxy
itself, so `scripts/run_task.py` rejects `CONTAINER_PROXY` for the current
restricted task policies.

Image pulls and Docker build downloads happen before untrusted task execution
and are configured at the Docker daemon/build layer; they are not task runtime
egress permissions.

## Optional upstream DNS for isolated Docker runs

If Docker's embedded resolver intermittently times out forwarding to the host
DNS stub (for example, `127.0.0.53`), configure reachable upstream IPv4 DNS
servers in the local `.env`:

```dotenv
CONTAINER_DNS=198.18.254.30,198.18.254.31
```

These example addresses belong to the diagnosed host's network; do not assume
they work elsewhere. `--container-dns IP,IP` overrides the environment setting.
Leave it unset to retain Harbor's default DNS behavior.

The launcher generates a Docker Compose overlay for the isolation sidecar,
shared by the task processes. It retains Harbor's original policy helper and
adds only TCP/UDP port 53 exceptions to the configured DNS IPs during nonempty
allowlist policies. `deny-all` removes those exceptions; ordinary API traffic
still uses the original hostname allowlist. This is not an HTTP proxy and does
not enable `CONTAINER_PROXY`. It neither changes host DNS nor restarts Docker.

Overlays and a snapshot of the installed Harbor helper are retained in
`/tmp/searchswe-dns-*` for the lifetime of the run. Do not remove them while a
run is active (including its separate verifier); they may be removed afterward.
Changing DNS does not fix unrelated TLS, API rate-limit, or authentication
failures. Verify permitted and denied destinations after upgrading Harbor.
