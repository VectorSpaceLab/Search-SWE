# Supported evaluation agents

[Documentation index](../README.md)

A setting selects one **harness + provider route + model** for the whole batch.
Use CLI 0.2.x with a checkout from the same release series.
The default is Codex + OpenRouter + `openai/gpt-6-luna` (`max` reasoning).

| Harness | CLI provider | Model selection | Coding-agent credential |
| --- | --- | --- | --- |
| Codex | `openrouter` | OpenRouter text/tool models using Responses | `AGENT_OPENROUTER_API_KEY` |
| Codex | `direct` | Model ID at an OpenAI/Codex-compatible endpoint | `AGENT_OPENAI_API_KEY`, `AGENT_OPENAI_BASE_URL` |
| Claude Code | `openrouter` | OpenRouter text/tool models using Messages, across model vendors | `AGENT_OPENROUTER_API_KEY` |
| Claude Code | `direct` | Claude model at the official Anthropic API | `AGENT_ANTHROPIC_API_KEY` |
| Pi | `openrouter` | OpenRouter text/tool models; full OpenRouter ID | `AGENT_OPENROUTER_API_KEY` |
| Pi | `direct` | `provider/model` from Pi's bundled API-key catalog | Selected provider's key and endpoint settings |

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

Pi 1.4.0 is pinned in the task images, with **40 API-key providers and 1,592 chat
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

Authentication uses API keys or provider tokens; subscription OAuth, ambient
AWS/GCP identities and custom Pi extensions are outside this workflow. Direct
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
for the native launcher and host requirements.
