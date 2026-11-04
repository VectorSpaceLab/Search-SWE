A cropped architectural photograph may show only a small part of a building. Build an image search system that finds additional photographs of that physical place, including views with different scale, viewpoint and occlusion. Each request supplies image IDs to exclude from its results.

The gallery is at `/task/data/corpus/`. Each row of `records.jsonl` contains `image_id`, `collection` and `image_path`. Image paths are relative to that directory. Original gallery photographs are supplied. Local image encoder weights are available at `/task/models/clip/`.

Provide executable `/app/build.sh` and `/app/run.sh` with their supporting files under `/app`. The build interface is:

```bash
/app/build.sh \
  --corpus /task/data/corpus \
  --index-dir /work/index
```

The query interface is:

```bash
/app/run.sh \
  --index-dir /work/index \
  --queries /work/input/queries.jsonl \
  --output /work/output/results.jsonl
```

Each input JSONL row contains `query_id`, `image_path` and `exclude_image_ids`. The image path is an absolute path to the current query image. Search the gallery excluding that request's listed IDs.

Return the same `query_id` and a `results` list of at most five distinct eligible images. Each result contains `image_id` and a finite numeric `score`, in nonincreasing score order. Write diagnostics to stderr. Public requests and relevance labels are at `/task/data/validation/queries.jsonl` and `/task/data/validation/labels.jsonl`. Labels contain `query_id` and `qrels` for matching images. Public query images are under `/task/data/queries/`. You may use these examples to develop and check the system.

Public and held-out relevance labels follow the Revisited Oxford/Paris Hard protocol: images labeled Hard are positives. Original Easy and Junk images are listed in each request's `exclude_image_ids`, not treated as negatives. Returning an excluded ID invalidates that query's result and gives it zero quality. Optimize binary nDCG@5, which rewards placing Hard positives near the top. Query scores are averaged within Oxford and Paris separately, then the two collection means receive equal weight.

You have two hours, 8 CPU cores, 32 GiB RAM, 100 GiB working storage and one GPU. The encoder is fixed. The build command has 3,600 seconds. The system must handle up to 140 requests in two calls of at most 70 requests, with an independent 2,700-second allowance per call. Additional pixel-based geometric verification may examine at most 20 candidate gallery images per request. Corpus-wide feature screening and gallery-only preprocessing are allowed within the runtime limits.

Process requests independently. Data, models and documentation are read-only. Generate the index at the passed path and include required runtime files under `/app`. The submitted files must work after a fresh start with the supplied gallery, fixed encoder and current queries. Completed valid JSONL rows remain usable after a timeout; missing or invalid rows are unsuccessful. A command failure other than timeout invalidates that call. Read `/task/docs/environment.md` and `/task/docs/available_resources.md`. Aim to return photographs of the same physical place rather than photographs that merely depict a similar style of building.

During verification, build and query commands run as a non-root user with `/app` and supplied inputs read-only. The passed index directory already exists and is writable during construction, but its parent directory is not writable. Create build files and temporary directories inside the index directory or the supplied `TMPDIR`; do not create siblings or rename the index directory itself. The completed index becomes read-only for retrieval. Query results, caches and temporary files belong in the writable output directory or the supplied `TMPDIR` and `XDG_CACHE_HOME`. Honor the passed paths rather than writing to `/app` or assuming a writable system temporary directory.
