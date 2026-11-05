# Available Resources

Use the supplied code corpus, training records, starting checkpoint and installed runtime.

## Local resources

- `/task/data/corpus.jsonl`: code corpus.
- `/task/data/train.jsonl`: training records.
- `/task/data/validation/`: public validation queries and relevance labels.
- `/task/models/bge-base-en-v1.5`: starting `BAAI/bge-base-en-v1.5` checkpoint, mounted read-only.
- `/app/starter/train.sh`: editable training starter.

Write trained checkpoints to the output path required by the task instruction.

Read `/task/docs/environment.md` for the installed Python environment, packages and system tools. Treat `/task` as read-only.

## Network and resource restrictions

Both task phases run without network access or task API keys. Use only the supplied data, model, installed Python packages and system tools. Do not add external checkpoints, datasets, labels or answer mappings.
