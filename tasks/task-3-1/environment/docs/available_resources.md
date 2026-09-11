# Available Resources

Use the local Python runtime, the standard library, task data, and packages
already installed in the base image. Do not download packages, models, corpora,
relevance judgments, or remote search results during the formal run.

The task data uses JSONL sparse vectors with opaque document, query, and term
IDs. Public queries, public relevance judgments, public term statistics, and
public regression data are available for local testing. Hidden queries and
hidden relevance judgments are not available to the submission.

NumPy is installed and may be used through its normal Python API. The formal
runtime is CPU-only, offline, and does not provide a GPU, transformer model,
package installer, remote service, or network dependency.

The submission must keep all required runtime state under the index directory
provided to `build.sh`. It must not depend on credentials, undeclared files,
background services, or files outside the task inputs and its own index.

See `environment.md` for runtime limits and `index_format.md` for the starter
index layout. The formal quality gates and latency reward are defined in
`/task/instruction.md`.
