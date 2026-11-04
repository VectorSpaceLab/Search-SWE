# Available Resources

Use the local Python runtime, task data and installed packages through their normal Python APIs. The formal run is CPU-only and offline. Do not download packages, models, corpora, relevance judgments or remote search results. No model weights or task API are supplied.

Documents, queries and terms use opaque IDs. Public queries, relevance judgments, term statistics and regression rankings are available for development. Hidden queries are supplied only to the formal search invocation; hidden relevance judgments are not available to submission code.

An editable unpruned retrieval starter is installed under `/app`; its read-only original is at `/baseline-starter`. You may modify or replace its index format and retrieval implementation while preserving the required executable interfaces. `/baseline-starter/README.md` provides optional implementation notes and index-layout details.

Store all persistent retrieval state under the index directory supplied to `build.sh`. Do not depend on credentials, undeclared files or background services. The coding agent's provider connection is not available to submitted programs.

See `environment.md` for installed software and resource limits. The task instruction defines the quality gates, timing contract and reward.
