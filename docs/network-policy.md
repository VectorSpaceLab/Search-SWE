# Runtime network policy

Search-SWE uses Harbor 0.22.0's `network_mode` and `allowed_hosts` fields.
Allowlists contain exact lowercase hostnames, not URLs, ports or paths, and
apply separately to each task and execution phase. Restricted tasks use an
independent trusted gateway for each agent/verifier environment, including when
an upstream proxy is configured. CPU/GPU task images remain unchanged.

## Default: direct access

No extra setup is required. The launcher uses
`hanhainebula/search-swe-egress:1.0.0`, pulls it if missing locally, and reuses it
on later runs. Leave `EGRESS_IMAGE` and `EGRESS_CONFIG` empty. `EGRESS_IMAGE` or
`--egress-image` can select a matching local build or repository digest.
Images are validated against this checkout before task containers start;
pull failures or incompatible images stop startup. Downloads use the Docker
daemon's network/proxy settings, not the task's proxy configuration.

Direct mode uses Docker DNS through the trusted gateway. If needed, set
`CONTAINER_DNS` (or `--container-dns`) to comma-separated reachable IPv4 DNS
servers. Only allowed host queries are forwarded; task processes cannot query
upstream or Docker DNS directly. Changing DNS does not repair TLS or API errors.

## Networks requiring a proxy

Use an HTTP(S) proxy with CONNECT support and an HTTPS DNS-over-HTTPS (DoH)
endpoint accessible through it. Create a JSON file outside task mounts and
build contexts, replacing the example address and hostname below:

```json
{
  "version": 1,
  "mode": "proxy",
  "image": "hanhainebula/search-swe-egress:1.0.0",
  "upstream": {"url": "http://192.0.2.10:8080"},
  "dns": {"doh_url": "https://resolver.example/dns-query"}
}
```

Point `.env` to the file, leaving other overrides empty:

```dotenv
EGRESS_CONFIG=/absolute/path/to/egress.json
EGRESS_IMAGE=
CONTAINER_DNS=
CONTAINER_PROXY=
```

`--egress-config PATH` overrides `EGRESS_CONFIG`. Relative CLI paths resolve
from the current directory; environment-variable paths resolve from the checkout.
Explicit config requires `image` and cannot be combined with image, DNS or general
container-proxy overrides. Do not add the proxy to task allowlists.

The proxy must be reachable **from Docker**; host `127.0.0.1` is not the host
inside a container. There is no fixed VPN product/port or automatic discovery.
SOCKS-only and TUN-only endpoints are not supported by this configuration.
For a hostname URL such as `https://proxy.example:8443`, also set
`upstream.address` to its reachable IPv4 address. Certificates are validated
against the URL hostname; custom CAs and client certificates are unsupported.
Loopback, link-local and task-local endpoints are rejected. Proxy URLs cannot
contain credentials, queries or fragments; DoH URLs cannot contain query parameters.

For proxy authentication, set `upstream.auth_file` to a JSON file containing
`{"username": "...", "password": "..."}`. Keep it outside task mounts/build
contexts, owned by the launcher user, with mode `0600` and parent mode `0700`.
Relative auth paths resolve from the config file; symlinks/hard links are rejected.
Only the trusted gateway receives these credentials.

Explicit direct config uses `"mode": "direct"`, no `upstream`, and
`"dns": {"servers": ["192.0.2.53"]}` with a reachable resolver (an optional UDP
port is accepted). An empty `dns` object selects Docker DNS. `version` and
`image` are still required. The launcher's `--dry-run` checks policy/config
compatibility without pulling images, reading proxy credentials or calling APIs.

## Supported runtime

- Native Linux amd64, local rootful Docker through a Unix socket, Harbor 0.22.0,
  and IPv4. Docker Desktop, remote/rootless Docker and userns remapping are unsupported.
- Direct mode supports public and restricted phases. **Proxy mode rejects any
  public phase**.
- Custom network topologies, extra capabilities/devices, host/control mounts,
  external/shared volumes and kept containers are rejected. Named volumes must
  be project-local plain Docker volumes.
- Authorization checks HTTP destinations and TLS SNI, not encrypted paths,
  bodies or Host headers/domain fronting at an approved origin.

## Isolation and recovery

The gateway starts in no-network mode, applies the phase baseline, then allows
task services to start. Task services cannot modify the firewall or forge trusted
traffic marks. Policy changes revoke old connections. Proxy, DNS or control
failure closes egress; there is no unrestricted fallback. A 30-second host-renewed
lease bounds revocation after loss of host control; trusted host clocks are required.
An already accepted upstream API operation cannot be undone by revocation.

Normal teardown removes each environment's owned resources and private settings,
while preserving images and host datasets. For leftovers after a failed cleanup:

```bash
python scripts/egress_cleanup.py
python scripts/egress_cleanup.py --directory /path/from/list
python scripts/egress_cleanup.py --directory /path/from/list --remove
```

These list, preview and remove one verified inactive instance respectively.
Recovery refuses active owners, foreign resources or a different Docker daemon.
Host logs under `egress/<instance>.log` record policies and kernel counters;
these counters are not HTTP request counts.

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
PYTHONPATH="$PWD${PYTHONPATH:+:$PYTHONPATH}" harbor run --path tasks/TASK_ID \
  --env scripts.harbor_environments:PhaseScopedDocker \
  --agent scripts.harbor_agents:PreinstalledCodex --model MODEL_ID \
  --ak version=0.147.0 \
  --allow-agent-host MODEL_API_HOST
```

For the supported official-Anthropic Claude Code mode, use the pinned wrapper,
an environment reference rather than a literal secret, and the fixed host:

```bash
PYTHONPATH="$PWD${PYTHONPATH:+:$PYTHONPATH}" harbor run --path tasks/TASK_ID \
  --env scripts.harbor_environments:PhaseScopedDocker \
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

These commands use the default direct gateway image and pull it if missing locally.
To select another matching image, add `--environment-kwarg egress_image=YOUR_IMAGE`. Manually using
`--env docker` selects installed Harbor and does not receive this checkout's
capability removal or old-connection revocation fixes.

Do not use `--allow-environment-host` for a coding-model endpoint: that changes
the environment baseline rather than only the agent phase. Do not add package
registries, source-code hosts, wildcard domains, or a general HTTP proxy to a
task allowlist. A general proxy reduces destination filtering to the proxy
itself, so `scripts/run_task.py` rejects `CONTAINER_PROXY` for the current
restricted task policies.

Image pulls and Docker build downloads happen before untrusted task execution
and are configured at the Docker daemon/build layer; they are not task runtime
egress permissions.

## Regression requirements

The [build and regression guide](../environments/egress/README.md#verification)
covers these enforcement requirements:

- Untrusted services cannot forge the gateway's firewall exemption marks or
  modify its rules; capabilities and namespace boundaries must enforce this.
- Tightening a policy terminates previously authorized tunnels and pooled
  connections, not merely rejects new connections.
- Agent, verifier, baseline, public, and no-network transitions are tested;
  phase allowlists must not be replaced with their union.
- Destination resolution works through the intended upstream path, including
  when local DNS returns NXDOMAIN, times out, or gives an incorrect address.
- Failure of the proxy, resolver, or policy update fails closed, without a
  direct/unfiltered fallback. TLS certificate validation remains enabled.
- The upstream endpoint is operator-configured, with no machine-specific IP,
  port, VPN product, or public DNS provider required by task packages.
