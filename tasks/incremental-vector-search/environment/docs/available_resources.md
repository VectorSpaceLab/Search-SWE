# Available Resources

Use only the supplied vectors and installed CPU libraries. No GPU, local model weights, external datasets, model downloads or network APIs are provided. Network access is disabled for the submitted program.

The corpus and warmup vectors are under `/task/data/corpus/<dimension>/`. Public validation inputs, exact neighbor IDs and squared distances are under `/task/data/validation/<dimension>/`. All supplied inputs and runtime resources are read-only.

Two optional reference implementations are available: `/task/reference/exact_search.py` performs exact L2 search, and `/task/reference/baseline_search.py` implements the public PQ baseline. Neither is required as a starting point. The current timing budgets and baseline recall statistics are in `/task/platform/limits.json`.

`/task/tools/profile_public.py` checks timing and the JSONL protocol using public probes. It does not compute retrieval quality or predict hidden-query results. For example:

```bash
python /task/tools/profile_public.py --dimensions 3072 --output /app/profiles/check1 -- bash /app/submission/run.sh
```

Run the profiler in the agent container and choose a fresh output directory outside `/app/submission`. Use the supplied validation neighbors to check retrieval quality separately. Submit only the implementation files under `/app/submission`; follow the task instruction for interfaces and resource limits.
