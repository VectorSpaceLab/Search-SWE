# Available Resources

The task runtime has no public network access. Use only the supplied candidate
documents, local `BAAI/bge-reranker-large` model, installed packages, and system
tools. Do not download or call replacement models, datasets, labels, retrieval
services, reranking services, or remote result mappings.

The coding agent's own model connection is a Harbor phase-scoped exception and
does not grant the submitted reranking system access to that model or to the
internet. The final system must run entirely from local task inputs.
