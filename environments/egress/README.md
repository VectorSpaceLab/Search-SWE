# Gateway builds and verification

For normal task runs, the launcher pulls the published gateway if it is missing
locally. Follow the
[direct/proxy configuration guide](../../docs/evaluation/network.md).

The image is shared by CPU/GPU tasks; it contains the network controller and
patched GOST, not the task runtime. The following instructions are for maintainers
changing or rebuilding it. Builds require native Linux amd64, local rootful
Docker, Harbor 0.22.0, Go **1.26.8** and curl. Verification also uses OpenSSL.

## Build from source

First build the helper base from the pinned Harbor installation. Its Dockerfile
pins the upstream image by digest; Docker may need registry access for this step.

```bash
SEARCHSWE_EGRESS_CONTEXT="$(python -c 'from importlib.metadata import version; assert version("harbor") == "0.22.0"; from harbor.environments.docker.docker import DockerEnvironment; print(DockerEnvironment._EGRESS_CONTROL_SIDECAR_CONTEXT_PATH)')"
docker build --platform linux/amd64 \
  --tag searchswe-egress-harbor:0.22.0 "$SEARCHSWE_EGRESS_CONTEXT"
```

Build the patched component, then the gateway. Use fresh output directories and
new tags for each build; the builders reject overwriting an existing image.

```bash
python scripts/egress/build_egress_component.py \
  --go /path/to/go1.26.8/bin/go \
  --base-image searchswe-egress-harbor:0.22.0 \
  --work-dir jobs/egress-build/component-local1 \
  --cache-dir jobs/egress-build/cache \
  --tag searchswe-egress-component:local1

python scripts/egress/build_egress_gateway.py \
  --component-image searchswe-egress-component:local1 \
  --tag searchswe-egress:local1 \
  --work-dir jobs/egress-build/gateway-local1 \
  --cache-dir jobs/egress-build/runtime-apks --download
```

Select the resulting gateway using `EGRESS_IMAGE=searchswe-egress:local1` for
direct mode, or the explicit config file's `image` field. The component image is
only a build input; task operators need the final gateway image alone.

The component builder applies `patch_gost.py` and runs its protocol regressions.
Source archives, module dependencies and runtime APKs are checksum-verified;
the gateway's source and package locks must match the checkout. Retain the build
manifests, source/license materials and caches with each distributed version.
For offline builds, use the component builder's `--offline` and omit the gateway
builder's `--download`. Missing or changed inputs fail the build.

## Verification

Network changes must preserve these enforcement requirements:

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

Host regressions include launcher selection, configuration, Harbor phase hooks,
Compose restrictions, credential handling, build inputs and ownership recovery:

```bash
python -B -m unittest discover -s tests/unit -v
```

For a pulled published image, a bounded direct TLS check uses a local HTTPS/DNS
fixture and verifies both successful allowed requests and receiving-end denials:

```bash
docker pull --platform linux/amd64 python:3.13-slim
python tests/integration/egress_direct_transport.py \
  --gateway-image hanhainebula/search-swe-egress:1.0.0 \
  --output jobs/egress-checks/direct-tls-01
```

For changes to network enforcement, run the relevant Docker regressions below.
Each command requires a fresh `--output jobs/egress-checks/NAME` directory and
`--gateway-image hanhainebula/search-swe-egress:1.0.0` (or your matching build):

| Script under `tests/integration/` | Coverage / additional arguments |
| --- | --- |
| `egress_lifecycle/run.py` | Filtering, phase changes, old connections, frozen-controller leases; run with `--transport direct` and `--transport proxy` |
| `egress_isolation/run.py` | Raw sockets, DNS and IPv6 bypass attempts; run both transports |
| `egress_transport/run.py` | HTTP/HTTPS proxies, authentication, TLS, DoH and H2; needs `--go /path/to/go` |
| `egress_full_trial.py` | Concurrent four-step Harbor trials with independent verifiers; run both transports |
| `egress_adapter_smoke.py` | Startup, cancellation and credential boundaries; add `--credential-probe` |
| `egress_orphan_smoke.py` | Host-driver death and owned-resource recovery; add `--credential-probe` |

`egress_s0/run.py` tests the patched component separately using
`--gost-image YOUR_COMPONENT_IMAGE --output jobs/egress-checks/component-01`.
Fixtures use local receivers and synthetic credentials, with no paid API calls.
Host tests alone do not establish network enforcement.

## Direct Harbor runs

Preview the Harbor command for the task, using the Search-SWE Python environment
from the checkout root. For example:

```bash
python scripts/evaluation/run_task.py --task agentic-search --agent codex \
  --openrouter --model openai/gpt-6-luna --dry-run
```

The preview shows the managed Codex agent, phase-scoped Docker adapter, credential
references and coding-model host. To run this example directly, prepare the task
assets, export the referenced variables and use the displayed command from the
checkout root. Use the launcher for native agents and Antigravity through
OpenRouter so it creates their private job configuration at startup. It also
handles task-specific preparation and GPU flags for the installed Harbor version.
An explicit device passed directly to the adapter must be a full GPU UUID.

Keep the coding endpoint in `--allow-agent-host` so access is scoped to the
agent phase. Use the [gateway configuration](../../docs/evaluation/network.md)
for an upstream proxy or a locally built image. Keep the task's declared
verifier policy and service credentials with the verifier.

Image pulls and Docker build downloads happen before untrusted task execution
and are configured at the Docker daemon/build layer; they are not task runtime
egress permissions.
