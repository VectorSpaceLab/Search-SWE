I need an embedding model and a search system for finding English documents with Khmer questions. Train the supplied multilingual-e5-large model for this collection and provide an executable indexing and retrieval pipeline.

Read `/task/docs/environment.md` and `/task/docs/available_resources.md` first. The collection at `/task/data/corpus.parquet` has `_id`, `title` and `text` columns. Three Khmer validation questions are available in `/task/data/validation/queries.jsonl`, with `id` and `question` fields; `/task/data/validation/answers.jsonl` has matching `id` values and English `answers`. No other labeled training data is supplied. The embedding backbone is at `/task/models/multilingual-e5-large`, and an optional local generative model is at `/task/models/Qwen3.5-9B`.

You have 6 hours, one GPU, 8 CPU cores, 32 GiB RAM and 100 GiB working storage. Network access is unavailable. Use only the supplied local resources. Treat `/task` as read-only and put your work under `/app`.

Save the trained weights to `/app/submission/model/model.safetensors`, overwriting that file if it exists. Put `config.json` and the unchanged tokenizer files in the same directory with their original filenames. Preserve the backbone architecture, parameter names, shapes and architecture configuration. The directory must be a complete, self-contained Hugging Face checkpoint that `AutoTokenizer.from_pretrained` and `AutoModel.from_pretrained` can load with `local_files_only=True` and `trust_remote_code=False`.

Provide executable `/app/build.sh` and `/app/run.sh`, with any supporting files they need under `/app`. They must accept the following arguments:

`/app/build.sh --corpus /task/data/corpus.parquet --index-dir /path/to/index` `/app/run.sh --index-dir /path/to/index --queries /path/to/queries.jsonl --output /path/to/results.jsonl`

`build.sh` must create the requested index directory from the supplied collection. The index directory does not initially exist; its parent exists and is writable. Construction has a 12-hour limit. A previously built collection index or cached retrieval results must not be used as the submission. `run.sh` must use the resulting index and support repeated invocations, with a 30-minute limit per invocation. The index is read-only during retrieval. Honour the supplied paths rather than assuming the example paths above. Build and retrieval run as separate non-root users, each with a writable working directory and `TMPDIR`; `/app` and task inputs are read-only. Use those writable directories for temporary files, honor the supplied output path, and do not write caches beside the checkpoint or assume a writable system temporary directory. The indexing and retrieval environment provides the same embedding backbone, one GPU, 8 CPU cores and 32 GiB RAM, without the optional generative model or network access.

Each query is a JSONL row with `id` and `question`:

`{"id":"query-001","question":"..."}`

For each query, write one JSONL row in the same order, containing the same `id`, `indices` and `scores`. Return 100 unique document positions, ranked by decreasing relevance score. Positions are zero-based row numbers in the supplied Parquet file. Scores must be finite numbers; ties are ordered by ascending document position. If a collection has fewer than 100 documents, return all its positions.

`{"id":"query-001","indices":[42,7,103],"scores":[0.91,0.85,0.72]}`

The abbreviated example illustrates the fields and ranking order. Do not write progress messages to the result file.

Maximize Recall@100 on the 1,000 hidden questions: a question succeeds when at least one of its first 100 retrieved documents contains an accepted answer as a contiguous, case-insensitive token sequence. Recall@100 is the fraction of questions that succeed. An invalid checkpoint, a failed or timed-out build or retrieval command, invalid retrieval output, or a confirmed task/resource-policy violation gives zero for the entire submission.
