# Task-2-5 Environment

The task runs in a prebuilt CPU-only container. The submission works in
`/app`; task data and documentation are mounted read-only under `/task/data` and
`/task/docs`.

The formal data contains a large corpus, public development data, and a hidden
query split. The corpus must be processed in a streaming or bounded-memory
fashion; loading all document terms into Python dictionaries may exceed the
memory limit.

The runtime provides 1 CPU worker, 32 GB memory, and no GPU. NumPy and the
Python standard library are available. No transformer model, package download,
credential, external service, or network access is required for the formal run.

Submission indexing and retrieval logic must be implemented in Python. Bash is
allowed only as a thin entry-point wrapper around Python. Native submission
source and compiled native submission executables are not allowed.

The verifier runs the corrected starter as the latency baseline. The starter
retains all corpus postings and performs no default DF, prefix, or other
posting-list pruning. Candidate wall time is compared with the starter wall
time measured by the verifier under the same workload and resource allocation.
