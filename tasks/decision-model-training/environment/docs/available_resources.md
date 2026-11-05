# Available Resources

Use the supplied labeled examples, starting checkpoint and installed runtime.

## Local resources

- `/task/data/examples.jsonl`: 80,000 labeled decision examples, available during development.
- `/task/models/Qwen3-0.6B`: read-only starting model files.

The examples are unavailable to the submitted system during final verification. Include any trained parameters and other required runtime files in `/app/submission`, as specified in the task instruction.

Read `/task/docs/environment.md` for the installed Python environment, packages and system tools. Treat `/task` as read-only.

## Network and resource restrictions

Development and final verification run without network access or task API keys. Use only the supplied local examples, model, installed packages and system tools. Do not use external datasets, additional pretrained weights, hidden examples or labels, precomputed answers, or hard-coded input-to-answer mappings.
