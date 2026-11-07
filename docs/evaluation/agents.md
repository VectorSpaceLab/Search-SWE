# Supported evaluation agents

[Documentation index](../README.md)

A setting selects one **harness + provider route + model** for the whole batch.
Use CLI 0.3.x with a checkout from the same release series.
The default is Codex + OpenRouter + `openai/gpt-6-luna` (`max` reasoning).

| Harness | CLI provider | Model selection | Coding-agent credential |
| --- | --- | --- | --- |
| Codex | `openrouter` | OpenRouter text/tool models using Responses | `AGENT_OPENROUTER_API_KEY` |
| Codex | `direct` | Model ID at an OpenAI/Codex-compatible endpoint | `AGENT_OPENAI_API_KEY`, `AGENT_OPENAI_BASE_URL` |
| Claude Code | `openrouter` | OpenRouter text/tool models using Messages, across model vendors | `AGENT_OPENROUTER_API_KEY` |
| Claude Code | `direct` | Claude model at the official Anthropic API | `AGENT_ANTHROPIC_API_KEY` |
| Pi | `openrouter` | OpenRouter text/tool models; full OpenRouter ID | `AGENT_OPENROUTER_API_KEY` |
| Pi | `direct` | `provider/model` from Pi's bundled API-key catalog | Selected provider's key and endpoint settings |
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
the checkout default. Exact versions are required. An explicit flag/saved version
takes precedence over native JSON `kwargs.version`, followed by the registry.

The shared installer prepares these five CLIs before the coding phase, verifies
the executable's actual `--version`, and records it in the agent log's
`harness.json`. Task Dockerfiles supply task dependencies. The verifier's judge
Codex pin is managed independently; changing the coding harness version preserves it.
Antigravity versions require a registered immutable archive URL and SHA-512 in
the central file. Other Harbor agents use their native installers and defaults;
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
Terminus 2 and ACP. Inspect the current list and native constructor parameters:

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
Harbor's own provider/model and authentication conventions. Common provider
credentials are mapped from agent-only variables such as `AGENT_OPENAI_API_KEY`
and `AGENT_OPENROUTER_API_KEY`; task submission and judge keys retain their roles.
Leave the native model field empty when the selected agent supplies a default. Harbor's registered
`oracle` and `nop` helpers are also available for task development.
In scripts, `--model ''` selects that native default and clears a saved model.

Grok Build and Junie select their native BYOK credentials from the `provider/model`
prefix; bare model names use their service authentication. Vibe defaults to
Mistral; choose `"kwargs": {"backend": "generic"}` in native configuration for
an OpenAI-compatible provider. The CLI maps that provider's key and endpoint to
Vibe's generic backend. Custom authentication and endpoints use the explicit
native configuration below.

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

Default control-plane hosts follow the published [Cursor network guide](https://cursor.com/docs/enterprise/network-configuration)
and [GitHub Copilot allowlist](https://docs.github.com/en/copilot/reference/copilot-allowlist-reference).
Add account-specific, regional or additional distribution hosts in the native JSON as needed.

Availability in `agents` describes Harbor's integrations. Actual use also depends
on the native agent's model, credentials, installer and task requirements.
The `atif` field reports trajectory support in Search-SWE; `atif_source` identifies
Harbor or the Search-SWE converter. `native_atif` reports upstream Harbor support. Tasks with trajectory
audits require a real `/logs/agent/trajectory.json`; their original checks apply
to every agent. The CLI checks the task's declared trajectory artifact before
preparing assets and requires an ATIF-capable route for those evaluations.
The `oracle`/`nop` development helpers can exercise primary grading; trajectory
audits still require their declared input. Pi direct, OpenRouter and native
routes share the Search-SWE event-stream-to-ATIF converter.
Inspect the chosen agent's official
setup when it needs project files, a subscription or cloud credentials.

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
