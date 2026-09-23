# Available Resources

The task runtime has no public network access. Use only the supplied vectors,
task data, installed Python packages, and system tools. Do not download models,
datasets, labels, result mappings, packages, or remote retrieval results.

The coding agent's own model connection is a Harbor phase-scoped exception and
does not grant the submitted search system access to that model or to the
internet. The final system must run entirely from local task inputs.
