# Available resources

Use the supplied full ARQMath corpus, five selected 2021 development queries and their complete qrels, installed
packages and system tools. No pretrained weights or algorithmic starter are supplied.

During development only, public model weights may be downloaded from
`huggingface.co`, `cdn-lfs.huggingface.co`, `cdn-lfs-us-1.hf.co`,
`cas-bridge.xethub.hf.co`, `cas-server.xethub.hf.co`, `transfer.xethub.hf.co`.
Pin immutable repository commits and document repository/revision/file SHA-256
in `/app/submission/README.md`. Include required weights in the submission.
These hosts are for models, not historical test data, labels, rankings or extra
datasets. No package downloads, remote inference, embedding/reranking APIs or GPU.

The final build/query process has no credentials and network syscalls are
restricted to Unix IPC. The coding agent's own provider connection is managed
by Harbor and does not authorize submission API use.

Do not retrieve hidden labels, hard-code query answers, inspect or modify
grading code/rewards, or bypass resource accounting. Complete rules are in the
task instruction. All formula-dependent preprocessing/training/indexing must
run inside the final build budget.


The other historical 2021 queries/labels are not authorized development inputs.
Both phases have two CPU cores and 4 GiB RAM, no swap/GPU. Final submitted files,
models, index and serving caches must fit the separate 40 MiB serving filesystem;
64 GiB total storage remains available for development/build scratch. Each final
query has 50 ms, including I/O. There are still 76 hidden official test queries.

Prepared submission/model/index artifacts must fit 34 MiB; the separate serving
filesystem is 40 MiB. See environment.md for exact accounting and failure rules.
