# Supported evaluation agents

[Documentation index](../README.md)

A setting selects one **harness + provider route + model** for the whole batch.
Use `search-swe info` to check whether the installed CLI and Harbor are compatible with your checkout.
The default is Codex + OpenRouter + `openai/gpt-6-luna` (`max` reasoning).

| Harness | CLI provider | Model selection | Coding-agent credential |
| --- | --- | --- | --- |
| Codex | `openrouter` | OpenRouter text/tool models using Responses | `AGENT_OPENROUTER_API_KEY` |
| Codex | `direct` | Model ID at an OpenAI/Codex-compatible endpoint | `AGENT_OPENAI_API_KEY`, `AGENT_OPENAI_BASE_URL` |
| Claude Code | `openrouter` | OpenRouter text/tool models using Messages, across model vendors | `AGENT_OPENROUTER_API_KEY` |
| Claude Code | `direct` | Claude model at the official Anthropic API | `AGENT_ANTHROPIC_API_KEY` |
| Pi | `openrouter` | OpenRouter text/tool models; full OpenRouter ID | `AGENT_OPENROUTER_API_KEY` |
| Pi | `direct` | `provider/model` from Pi's bundled API-key catalog | Selected provider's key and endpoint settings |
| Antigravity CLI | `openrouter` | OpenRouter text/tool models using Chat Completions | `AGENT_OPENROUTER_API_KEY` |
| Any registered Harbor agent | `native` | Native model ID, or the agent's default | Selected agent's `AGENT_*` variables and optional native configuration |

## Harness versions and installation

Defaults live in [`src/search_swe/data/harnesses.toml`](../../src/search_swe/data/harnesses.toml).
The CLI uses the selected checkout's registry for the whole batch:

| Harness | Default version |
| --- | --- |
| Codex | `0.164.0` |
| Claude Code | `2.1.309` |
| Pi | `1.4.0` |
| Gemini CLI | `0.67.0` |
| Antigravity CLI | `1.5.2` |

Override a version with `--agent-version 0.164.0`, or save
`SEARCH_SWE_AGENT_VERSION` in `.env`. Use `--agent-version default` to return to
the checkout default. Use an exact version for an override. An explicit flag/saved version
takes precedence over native JSON `kwargs.version`, followed by the registry.

The shared installer prepares these five CLIs before the coding phase, verifies
the executable's actual `--version`, and records it in the agent log's
`harness.json`. Task Dockerfiles supply task dependencies. The verifier's judge
Codex pin is managed independently; changing the coding harness version preserves it.
Antigravity versions require a registered immutable archive URL and SHA-512 in
the central file. Other Harbor agents use their native setup and defaults;
explicit version requests must pass actual CLI verification. Agents without a
CLI version command are controlled by Harbor's own version.

Installed programs are cached on the host at
`$XDG_CACHE_HOME/search-swe/harnesses` (default `~/.cache/search-swe/harnesses`),
or `SEARCH_SWE_HARNESS_CACHE`. A custom directory must be owned by the invoking
user with mode `0700`. Entries are keyed by the exact task image, version and
installer recipe, checked for integrity, and locked during concurrent installs.
The cache contains installation files; credentials and run outputs stay in their
own private paths. First use needs package-download access; later matching runs
reuse the cache. `--offline` concerns task assets/model metadata, while harness
installation and model API calls may still need network.

## Harbor native agents

CLI 0.3.0+ discovers agents from the installed Harbor registry, including
Antigravity CLI/SDK, Gemini CLI, Cursor, Copilot, OpenCode, OpenHands, Aider,
Terminus 2 and ACP. Inspect the current list and the native options for an agent:

```bash
search-swe agents
search-swe agents --agent antigravity-cli --json
```

Choose any listed agent in the wizard, or select it explicitly:

```bash
search-swe configure --agent antigravity-cli --provider native \
  --model gemini/gemini-2.5-flash
search-swe run TASK --agent antigravity-cli --provider native \
  --model gemini/gemini-2.5-flash
```

The wizard requests `AGENT_GEMINI_API_KEY` for this setting. Native routes use
Harbor's own provider/model and authentication conventions. When a shared `.env`
contains keys for several providers, the CLI selects the coding key and endpoint
for the model's provider. For example, native Pi with `openrouter/openai/gpt-4o`
uses `AGENT_OPENROUTER_API_KEY`.
Leave the native model field empty when the selected agent supplies a default. Harbor's registered
`oracle` and `nop` helpers are also available for task development.
In scripts, `--model ''` selects that native default and clears a saved model.

For native agents with BYOK, use a `provider/model` ID to select provider credentials. On Harbor
0.25 and later, Kimi Code, Grok Build and Junie can also infer the provider from
recognized model names such as `gpt-4o`. Copilot keeps GitHub authentication
for bare catalog names and accepts an explicit provider such as
`openrouter/openai/gpt-4o`. Vibe selects its generic backend for non-Mistral
providers. On Harbor 0.22–0.24, set `"kwargs": {"backend": "generic"}`
explicitly for Vibe and use provider prefixes for Grok Build and Junie.

### Native configuration

Pass `--agent-config .env.agent.json`, or save its path as
`SEARCH_SWE_AGENT_CONFIG`. The CLI resolves relative paths from the selected
checkout; absolute paths also work. The JSON supports these fields:

```json
{
  "env": {"GEMINI_API_KEY": "${AGENT_GEMINI_API_KEY}"},
  "kwargs": {"reasoning_effort": "high"},
  "extra_allowed_hosts": ["generativelanguage.googleapis.com"],
  "setup_hosts": [],
  "files": {}
}
```

`kwargs` are the selected Harbor agent's native parameters, including `version`
where supported. The launcher puts them in a private job file instead of command
arguments. Credential values belong in the private `.env`; the native `env`
section references them with `${AGENT_VARIABLE_NAME}`. An explicit `env` block
selects its own authentication strategy, including native OAuth or cloud auth.
Configure authentication selectors and cloud profiles in that block; native runs
isolate host credentials and provider selectors before applying the selected env.
On Harbor 0.25 and later, `kwargs.model_api_key_name` selects the variable that
holds the model credential inside the agent. For example, selecting `TEAM_KEY`
prompts for `AGENT_TEAM_KEY`. To use an existing key, map `TEAM_KEY` to its
`${AGENT_VARIABLE_NAME}` reference in `env`.
`files` maps `${AGENT_AUTH_FILE}` to an absolute container file path for an agent
that needs an uploaded credential file; the variable contains its local path.
The agent-specific env/config must point at that container path. Harbor adapters
that themselves upload host credential files can use their native path variables.

`extra_allowed_hosts` lists exact model/authentication domains for the coding
phase. Provider defaults and configured base URLs supply known model hosts;
configure additional service domains required by the chosen agent. `setup_hosts`
adds package distribution domains for trusted installation only. The native
adapter uses the shared installer for the managed CLIs and Harbor's installer
for other agents, then restores the task's network
policy before running the agent, including when setup fails. Task files and
verifier network permissions retain their declared settings.

With Harbor 0.26 or later, native Antigravity CLI uses the host in
`env.AGY_LLM_GATEWAY_URL`. Bind `AGY_LLM_GATEWAY_API_KEY` to the gateway
credential in the same `env` block. Use this single endpoint for gateway
mode. The CLI reports a configuration error if a provider setting redirects
the connection to a different address. For Google Application Default Credentials
(`AGY_ADC_AUTH=true`), choose Gemini 3 Flash or newer and list your project's
authentication and model hosts in `extra_allowed_hosts`.

Default control-plane hosts follow the published [Cursor network guide](https://cursor.com/docs/enterprise/network-configuration)
and [GitHub Copilot allowlist](https://docs.github.com/en/copilot/reference/copilot-allowlist-reference).
Add account-specific, regional or additional distribution hosts in the native JSON as needed.

Availability in `agents` describes Harbor's integrations. Actual use also depends
on the native agent's model, credentials, installer and task requirements.
Check the agent's setup instructions when it needs project files, a subscription
or cloud credentials.
The `atif` field reports trajectory support in Search-SWE; `atif_source` identifies
Harbor or the Search-SWE converter. `native_atif` reports upstream Harbor support. Tasks with trajectory
audits require a real `/logs/agent/trajectory.json`; their original checks apply
to every agent. The CLI checks the task's declared trajectory artifact before
preparing assets and requires an ATIF-capable route for those evaluations.
The `oracle`/`nop` development helpers can exercise primary grading; trajectory
audits still require their declared input. Pi direct, OpenRouter and native
routes export ATIF from Pi's event stream. Use ATIF `prompt_tokens` to compare
Pi runs across Harbor versions. It includes uncached input, cache reads and
cache writes. Harbor 0.22 and 0.23 omit cache writes from the trial summary's
`n_input_tokens`.

On Harbor 0.23 and later, Antigravity usage in `agent/antigravity-stream.jsonl`
can supply trial token totals even when individual ATIF steps omit usage.
Reported cost is an estimate when model pricing is available.

## Antigravity CLI through OpenRouter

Use CLI 0.3.1 or later in the 0.3.x series with a checkout containing this
integration. Set `AGENT_OPENROUTER_API_KEY` in the checkout's private `.env`.

```bash
search-swe run TASK --agent antigravity-cli --provider openrouter \
  --model google/gemini-4-argon --reasoning-effort high
```

The route uses a loopback bridge in the agent container to translate agy's
Gemini requests to OpenRouter Chat Completions. Use the full OpenRouter model
ID. Effort accepts `default` (agy's model default), `low`, or `high`.
The bridge transfers tool calls, results, and reasoning details across turns.
OpenRouter is the coding-model endpoint for this route.

## Claude Code and Codex subscriptions

Both use `--provider native` with explicit credentials in `--agent-config`.
Prepare the following files in your Search-SWE checkout; the CLI reads its `.env`.
Choose a task and a model available to your subscription, using the harness's
model ID. Add `--dry-run` to preview either command, or replace `run` with
`configure` to save the setting before launching.

### Claude Code

With Claude Code installed on the host, run `claude setup-token` and sign in to
your subscription account. Put the resulting token in the checkout's private
`.env`:

```dotenv
AGENT_CLAUDE_CODE_OAUTH_TOKEN=YOUR_SUBSCRIPTION_TOKEN
```

Create `.env.claude-subscription.json`:

```json
{
  "env": {
    "CLAUDE_CODE_OAUTH_TOKEN": "${AGENT_CLAUDE_CODE_OAUTH_TOKEN}",
    "ANTHROPIC_BASE_URL": "https://api.anthropic.com"
  },
  "extra_allowed_hosts": [
    "claude.ai", "claude.com", "platform.claude.com", "console.anthropic.com"
  ]
}
```

```bash
search-swe run TASK --agent claude-code --provider native \
  --model CLAUDE_MODEL_ID --reasoning-effort default \
  --agent-config .env.claude-subscription.json --concurrency 1
```

The explicit `env` selects OAuth credentials; the URL keeps requests on the
official service even if an API endpoint was saved for another setting. Generate
a new token when it expires. See Claude Code's
[setup-token command](https://code.claude.com/docs/en/cli-reference) and
[OAuth token configuration](https://code.claude.com/docs/en/env-vars#variables).

### Codex

With Codex installed on the host, sign in with ChatGPT using file-based storage:

```bash
codex -c 'cli_auth_credentials_store="file"' login
```

For a headless host, add `--device-auth` if your account enables device login,
or securely copy the login file from a machine with a browser. The file is
`auth.json` under your `CODEX_HOME` (normally `~/.codex`). Set its **absolute host
path** in the checkout's private `.env`; environment-file values are literal:

```dotenv
AGENT_CODEX_AUTH_JSON_PATH=/absolute/path/to/.codex/auth.json
```

Create `.env.codex-subscription.json`:

```json
{
  "env": {
    "CODEX_AUTH_JSON_PATH": "${AGENT_CODEX_AUTH_JSON_PATH}",
    "OPENAI_BASE_URL": "",
    "OPENAI_API_BASE": ""
  },
  "extra_allowed_hosts": ["chatgpt.com", "auth.openai.com"]
}
```

```bash
search-swe run TASK --agent codex --provider native \
  --model CODEX_MODEL_ID --reasoning-effort default \
  --agent-config .env.codex-subscription.json --concurrency 1
```

Harbor uploads the host's login file into each task container. Empty endpoint
overrides let Codex use its subscription endpoint even when other API addresses
are saved. This is a copy: refreshed container credentials are not written back
to the host file. Renew the host login if later runs report expired or revoked
credentials. See [Codex authentication](https://learn.chatgpt.com/docs/auth).

### Scope and checks

Keep `.env` and the login file private with mode `0600`. The `.env.*.json` files
above are Git-ignored and contain references rather than credential values.
Subscription access covers the **coding agent**; selected tasks still need their
own judge and submission API credentials. Model access and usage limits follow
your account, so start with one task at a time.

The examples have been checked offline against the native configuration and
Harbor authentication paths; a real subscription evaluation has not been run.
`--dry-run` checks configuration without testing account access. Additional
account-specific authentication domains belong in `extra_allowed_hosts`; see
the [network guide](network.md) for host proxy setup.

## Integrated OpenRouter routes

OpenRouter selection supports search and manual IDs. Suggestions use the
catalog's text, tool and endpoint metadata. An accepted ID is not a completed
compatibility test: model availability, tool behavior and supported reasoning
levels depend on the provider. Use `--reasoning-effort default` with a new model
to keep the harness/model default.

Claude Code uses OpenRouter's native Messages endpoint. Its main, Opus, Sonnet,
Haiku and subagent roles all use the selected model. OpenRouter
[guarantees its Claude Code integration for Anthropic's first-party provider](https://openrouter.ai/docs/cookbook/coding-agents/claude-code-integration);
other vendors can be selected when they expose Messages, with compatibility
dependent on that model and provider.

## Pi API-key providers

The bundled Pi 1.4.0 catalog contains **40 API-key providers and 1,592 chat
models**. List providers and exact IDs offline, without installing Pi on the host:

```bash
search-swe pi-models
search-swe pi-models --provider google
search-swe pi-models --provider xiaomi --json
```

Each model listing shows directly usable `--provider` and `--model` flags.
Models using the OpenRouter route are listed as `vendor/model`, ready for
`run --agent pi --provider openrouter --model vendor/model`. JSON also includes
Pi's full `native_id` for direct/native integration.

The wizard selects the API provider first, then searches its models, and asks
only for that provider's missing configuration. Pi's `OPENAI_API_KEY`,
`ANTHROPIC_API_KEY`, `OPENROUTER_API_KEY` and `HF_TOKEN` come from the host's
`AGENT_OPENAI_API_KEY`, `AGENT_ANTHROPIC_API_KEY`, `AGENT_OPENROUTER_API_KEY` and
`AGENT_HF_TOKEN`, respectively. Other provider key names follow Pi's
[official configuration](https://github.com/earendil-works/pi/blob/v1.4.0/packages/coding-agent/docs/providers.md).

| Provider | Additional setup |
| --- | --- |
| Azure | `AZURE_OPENAI_BASE_URL` or `AZURE_OPENAI_RESOURCE_NAME`; optional `AZURE_OPENAI_API_VERSION` and `AZURE_OPENAI_DEPLOYMENT_NAME_MAP` |
| Cloudflare Workers AI | `CLOUDFLARE_ACCOUNT_ID` |
| Cloudflare AI Gateway | `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_GATEWAY_ID` |
| Amazon Bedrock | `AWS_BEARER_TOKEN_BEDROCK`, `AWS_REGION` |
| Google Vertex AI | `GOOGLE_CLOUD_API_KEY` for express/API-key mode |

The Pi `direct` route uses API keys or provider tokens. Pi's native route uses
Harbor's own configuration and authentication. Direct
models come from the pinned catalog. New OpenRouter models use the native Pi
Chat Completions adapter with live/cached metadata resolved before the run.
Only the coding-agent phase gains access to the selected endpoint.

## Examples

```bash
search-swe run TASK --agent claude-code --provider openrouter \
  --model openai/gpt-6-luna --reasoning-effort default
search-swe run TASK --agent pi --provider direct \
  --model google/gemini-2.5-flash --reasoning-effort default
search-swe run TASK --agent pi --provider openrouter \
  --model deepseek/deepseek-v4.1-flash --reasoning-effort default
```

Coding-agent credentials are independent of verifier credentials and the
[47/17-model submission-key profiles](submission-models.md). See
[CLI configuration](cli.md) for the wizard and [evaluation setup](runtime.md)
for the single-task launcher and host requirements.
