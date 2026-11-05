# Available Resources

Use the supplied vectors, filter metadata and installed runtime.

## Local resources

- `/task/data/corpus/`: supplied vectors and filter metadata.
- `/task/data/validation/`: public queries and reference answers.
- `/task/data/example/`: small example inputs.
- `/task/docs/data-format.md`: binary formats and row-ID mappings.

Read `/task/docs/environment.md` for the installed Python environment, packages and system tools. Treat `/task` as read-only.

## Network and resource restrictions

The task runtime has no public network access or task API keys. Use only the supplied vectors, task data, installed Python packages, and system tools. Do not download models, datasets, labels, result mappings, packages, or remote retrieval results.

The final system must run entirely from local task inputs.

Do not use hidden evaluator data or hard-coded query-to-result mappings, or manipulate the verifier, recorded trajectory or resource accounting.
