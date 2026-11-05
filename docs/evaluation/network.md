# Runtime network policy

[Documentation index](../README.md)

Task `network_mode` and `allowed_hosts` settings apply independently to the
agent and verifier. Restricted environments use a trusted gateway to enforce
exact allowed hostnames. Normal evaluation needs no extra network configuration.

## Default: direct access

Leave `EGRESS_CONFIG` and `EGRESS_IMAGE` empty. The launcher pulls
`hanhainebula/search-swe-egress:1.0.0` when needed and checks compatibility before
starting task containers. Docker's network settings control image downloads.

Direct mode uses Docker DNS through the gateway. If a different resolver is
needed, set `CONTAINER_DNS` to comma-separated reachable IPv4 servers. Only
allowed queries are forwarded; DNS changes do not fix TLS or API errors.

## Networks requiring a proxy

Use an HTTP(S) proxy supporting CONNECT and an HTTPS DNS-over-HTTPS endpoint
reachable through it. Create a JSON file outside task mounts/build contexts:

```json
{
  "version": 1,
  "mode": "proxy",
  "image": "hanhainebula/search-swe-egress:1.0.0",
  "upstream": {"url": "http://192.0.2.10:8080"},
  "dns": {"doh_url": "https://resolver.example/dns-query"}
}
```

Replace the example addresses, then set the checkout `.env`:

```dotenv
EGRESS_CONFIG=/absolute/path/to/egress.json
EGRESS_IMAGE=
CONTAINER_DNS=
CONTAINER_PROXY=
```

The proxy must be reachable **from Docker**. Host `127.0.0.1` refers to the
container itself. Use a reachable IPv4 address; for a hostname URL such as
`https://proxy.example:8443`, also set `upstream.address` to that address.
TLS certificates are checked against the URL hostname.

| Setting | Requirement |
| --- | --- |
| Explicit config | `version` and `image` are required; leave image, DNS and general container-proxy overrides empty |
| Proxy endpoint | HTTP(S) CONNECT; SOCKS/TUN-only endpoints, custom CAs and client certificates are unsupported |
| Proxy URL | No embedded credentials, query or fragment; loopback, link-local and task-local endpoints are rejected |
| DoH URL | HTTPS, without query parameters |
| Proxy authentication | Optional `upstream.auth_file`, described below |

For authentication, use a separate JSON file with
`{"username": "...", "password": "..."}`, owned by the launcher user with mode
`0600` and parent mode `0700`. Keep it outside task mounts/build contexts;
symlinks and hard links are rejected. Relative auth paths resolve from the
config file. Only the gateway receives these credentials.

`EGRESS_CONFIG` paths resolve from the checkout. The native launcher's
`--egress-config PATH` overrides it and resolves from the current directory.
Its `--dry-run` checks policy/config compatibility without pulling images or
reading proxy credentials. Configure image pulls and builds at the Docker
layer; runtime proxy settings apply to task traffic.

## Supported runtime

- Native Linux amd64, IPv4, Harbor 0.22.0 and local rootful Docker through a
  Unix socket, without user namespace remapping. Docker Desktop and remote or
  rootless Docker are unsupported.
- Direct mode supports public and restricted phases. **Proxy mode supports
  `allowlist` and `no-network` phases.**
- Task services use the enforced topology and project-local plain Docker volumes.
  Explicit `CHECKPOINT_RESTORE` is supported for mapped-file accounting. The exact
  `SYS_PTRACE` + `CHECKPOINT_RESTORE` pair is also supported on the main service of
  a separate single-step verifier. The host identifies this role from Harbor's
  `tests/` environment context, independently of trial-name length. Submitted
  processes must still drop all capabilities. Other extra capabilities/devices,
  host/control mounts, external/shared volumes,
  custom networks and kept containers are rejected.
- Tasks can opt into `[metadata] public_inputs_readable = true`. Before
  build/start, the adapter ensures that their task-local read-only `/task/`
  inputs also declared in the agent main service are readable and directories
  traversable by submission users. This restores checkout/cache permissions
  without changing contents, ownership or write permissions. Hidden verifier
  inputs and writable mounts are excluded; links and special files requiring
  unsafe traversal or permission changes are rejected.
- Filtering checks HTTP destinations and TLS SNI; it does not inspect encrypted
  paths, bodies or domain fronting at an allowed origin.

## Task-owned phase policies

Each task's `task.toml` declares its policy; its resource document explains
submission permissions. Allowlists use exact lowercase hostnames, without URLs,
ports or paths.

| Configuration | Scope |
| --- | --- |
| `[environment]` | Baseline network policy |
| `[agent]` | Agent-phase override, plus the launcher-selected coding-model host |
| `[verifier]` | Separate verifier policy, including its required judge endpoints |

The coding-model host comes from the selected direct endpoint, or `openrouter.ai`
for OpenRouter. Agent tools are preinstalled in task images. A verifier's judge
access does not grant the submitted program that access; task-local confinement
and separate credentials enforce submission permissions. Leave `CONTAINER_PROXY`
unset and route proxies through the gateway configuration above.

## Isolation and recovery

Each environment has an independent gateway. Policy changes revoke old
connections; proxy, DNS or control failures close egress. A 30-second host-renewed
lease bounds revocation after host-control loss and requires trustworthy host
clocks. An API operation already accepted upstream may still finish.

Normal cleanup removes owned resources and private settings, preserving images
and datasets. For leftovers, list instances, preview one, then remove it:

```bash
python scripts/egress/egress_cleanup.py
python scripts/egress/egress_cleanup.py --directory /path/from/list
python scripts/egress/egress_cleanup.py --directory /path/from/list --remove
```

Recovery refuses active owners, foreign resources or another Docker daemon.
Host `egress/<instance>.log` files record policies and kernel counters, rather
than HTTP request counts.

## Advanced configuration

An explicit direct config uses `"mode": "direct"`, `version`, `image`, no
`upstream`, and `"dns": {"servers": ["192.0.2.53"]}` (optional UDP port).
An empty `dns` object selects Docker DNS. For a matching local gateway build,
use `EGRESS_IMAGE` or the native `--egress-image`; explicit configs select their
image inside the JSON file.

For [direct Harbor calls](../../environments/egress/README.md#direct-harbor-runs),
[image builds](../../environments/egress/README.md#build-from-source), or
[enforcement regressions](../../environments/egress/README.md#verification), use
the gateway developer guide.
