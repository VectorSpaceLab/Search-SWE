I need to answer business questions using data spread across several databases. Before writing SQL, I need to find the relevant tables and the columns connecting them. Build an executable search engine that takes a natural-language question and returns five candidate tables with up to six joins that together support the question. Generating or executing SQL is outside this task.

Read `/task/docs/environment.md` and `/task/docs/available_resources.md` for the runtime and permitted APIs and models. Those APIs may be used during indexing and querying. Both phases have 16 CPUs, 32 GiB RAM, 100 GiB storage and no GPU. You have 120 minutes for implementation and validation.

`/task/data/catalog.json` contains `schema_version`, `tables` and `joins`. Tables have opaque `table_id` and database `group_id` values, original names, descriptions, columns, row counts and incomplete sample rows. Columns have table-scoped IDs, names, types and primary-key metadata; multiple `primary_key: true` columns jointly form the key. The public `joins` list defines column-level equality relationships. Questions do not identify their database group. The entire catalog is available for indexing and search.

The 10 public validation questions are in `/task/data/validation/queries.jsonl`, with labels in `/task/data/validation/labels.jsonl`. Each label contains `query_id` and `acceptable_plans`, whose entries have `table_ids` and `joins`. Final evaluation uses 10 hidden questions. Full databases and source SQL are not supplied. Implement genuine catalog retrieval; do not hard-code question-specific answers, obtain external benchmark SQL or answers, access hidden grading files, or tamper with evaluation.

Put `build.sh`, `search.sh` and all supporting files and additional dependencies in `/app/submission`, which starts empty. Only this submission directory transfers to a fresh verifier, where commands run as an unprivileged user with the submission read-only.

To prepare the catalog for search, the verifier invokes:

```bash
bash /app/submission/build.sh \
  --corpus /task/data/catalog.json \
  --index-dir /work/index
```

The index directory exists and is empty. Build once, place all index files there, and exit with status 0 within 1,200 seconds. The index may contain only regular files and directories totaling at most 8 GiB.

After a successful build, it starts the search process with:

```bash
bash /app/submission/search.sh \
  --index-dir /work/index
```

Print `{"ready":true}` followed by a newline within 30 seconds, then keep the process alive to read one JSON query per stdin line until EOF. Each query contains exactly `query_id` and `question`, for example:

```json
{"query_id":"opaque-query-id","question":"A natural-language business question."}
```

For each query, emit and flush one JSON response on stdout within 20 seconds of receiving it; send diagnostics to stderr. API calls count toward all deadlines. Evaluation queries arrive sequentially in a fixed order; echo the received opaque query ID. An unscored warm-up precedes evaluation, with a restart on failure.

Each response must be one JSON line of at most 65,536 bytes including its newline, with exactly these fields and real catalog IDs:

```json
{"query_id":"opaque-query-id","table_ids":["tbl_A","tbl_B","tbl_C","tbl_D","tbl_E"],"joins":[{"left_table":"tbl_A","left_column":"c_000","right_table":"tbl_B","right_column":"c_001"}]}
```

Return exactly five distinct table IDs and zero to six distinct public joins. Each join must contain exactly the four fields shown and reference real columns of returned tables. Duplicate JSON keys and extra fields are invalid. Table order, join order and reversing join endpoints do not affect scoring. Extra valid candidates are allowed within the budgets; the full candidate set need not be connected or belong to one database group.

A question earns 1 only when a valid response contains every table and join of the same acceptable plan, and 0 otherwise. The score is the mean across all evaluation questions, including failures, with no partial credit. Missing, late or invalid responses fail that question; the service may restart for later queries. Build failure, index-limit violation or a confirmed task/resource-policy violation gives zero overall.
