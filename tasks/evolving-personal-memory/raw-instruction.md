# Personal-History Search and Answering

## Task Description

Build a personal-memory search system that answers questions using a person's conversation history up to a specified session. It will be used repeatedly as the person's circumstances change, so answers need to reflect the history available at the requested cutoff.

## Requirements

### Resource limits and workload

- The environment provides 8 CPU cores, 32 GiB RAM, 100 GiB storage and no GPU.
- You have two hours for development.
- Index construction has a 30-minute limit.
- A search call may contain up to 300 questions and has a 30-minute limit.
- Each answer process has up to ten minutes after launch, with up to eight answer processes running concurrently and a shared two-hour answer-phase budget.
- Write each output to the requested path.
- The system must support repeated calls using the same index.

### Build interface

Build the index once with:

```bash
/app/build.sh \
  --corpus /task/data/corpus \
  --index-dir /path/to/index
```

The index directory persists across search calls. During verification, build and search run as a non-root user with `/app`, the corpus and query inputs read-only. The passed index directory already exists and is writable, but its parent is not writable. Put generated files, search caches and build temporary directories inside `--index-dir` or the supplied `TMPDIR`; do not create siblings or rename the index directory itself. The index remains writable across search calls. Write search results to the passed output path, whose parent is writable, and honor all supplied paths.

### Search interface and output contract

Each search call receives a JSONL file of questions and writes one JSONL result per question:

```bash
/app/search.sh \
  --index-dir /path/to/index \
  --queries /path/to/queries.jsonl \
  --output /path/to/retrievals.jsonl
```

For example, an input row and its corresponding output row are:

```json
{"query_id":"QUERY_PLACEHOLDER","persona_id":"PERSONA_PLACEHOLDER","cutoff_session":10,"question":"QUESTION_PLACEHOLDER"}
```

```json
{"query_id":"QUERY_PLACEHOLDER","record_ids":["RECORD_PLACEHOLDER"]}
```

Return only `query_id` and `record_ids`. Return at most 350 unique record IDs for the specified person, with session numbers no greater than `cutoff_session`. An empty list is allowed.

### Answer interface and isolation

The returned IDs are checked and used to assemble an answer request containing the complete original records. For example:

```json
{
  "query_id": "QUERY_PLACEHOLDER",
  "persona_id": "PERSONA_PLACEHOLDER",
  "cutoff_session": 10,
  "question": "QUESTION_PLACEHOLDER",
  "records": [
    {
      "record_id": "RECORD_PLACEHOLDER",
      "persona_id": "PERSONA_PLACEHOLDER",
      "session_id": 3,
      "date": "DATE_PLACEHOLDER",
      "text": "COMPLETE_RECORD_TEXT_PLACEHOLDER"
    }
  ]
}
```

Answer this request with:

```bash
/app/answer.sh \
  --input /path/to/request.json \
  --output /path/to/answer.json
```

The output is a JSON object containing only the same `query_id` and a nonempty natural-language `answer`:

```json
{
  "query_id": "QUERY_PLACEHOLDER",
  "answer": "ANSWER_PLACEHOLDER"
}
```

Each answer runs as a separate non-root process with its own writable output and temporary directories. Use the supplied `TMPDIR` and `XDG_CACHE_HOME` for temporary files and caches. The answer process can read its read-only current request, `/app/answer.sh`, supporting files under `/app/answer/`, installed system libraries and its temporary directory. It cannot read the complete corpus, index, search outputs or other requests. Do not use links in the answer directory to access files outside it. The process receives the permitted generative API credential; it does not receive retrieval API credentials. You may process the supplied records in batches and make multiple permitted LLM calls. Record text is supplied in full and may exceed one model call's context capacity.

## Available Validation Data

The complete conversation collection is at `/task/data/corpus/records.jsonl`. Each record contains `record_id`, `persona_id`, `session_id`, `date` and `text`. Public questions and their answer criteria are at `/task/data/validation/queries.jsonl` and `/task/data/validation/labels.jsonl`. Use these examples to check your system.

## Expected Artifacts

Submit executable `/app/build.sh`, `/app/search.sh` and `/app/answer.sh`, together with any supporting files under `/app`. Put supporting answer-side code and configuration under `/app/answer/`. Build and search may use the corpus and index; answer must work from the current request alone. Answer-side files must contain reusable code and configuration, not stored conversation facts or answers.

```text
/app/
├── build.sh
├── search.sh
├── answer.sh
└── answer/  # supporting answer-side code and configuration
```

## Verification

After development, Harbor transfers the declared artifacts to a separate verifier and evaluates the system on the held-out split. The verifier checks the following items:

1. **Task and resource compliance.** The submission must use the supplied inputs and permitted resources, follow stage isolation, and avoid hidden labels or hard-coded evaluation answers.
2. **Executable behavior.** The required commands must follow the interfaces, filesystem permissions and time limits above and support the specified repeated calls.
3. **Output validity.** Results must satisfy the task-specific schema, identifiers, bounds and ordering rules. Missing required executables or a failed or timed-out build gives zero for the entire submission. A search timeout preserves valid completed rows; any other search-command failure invalidates that call's results. Missing, duplicate or invalid retrieval results, and missing, invalid, failed or timed-out answers, score zero for the affected questions. Valid results for other questions remain usable, and all held-out questions remain in the average.
4. **Search quality.** Three independent judge configurations vote on each memory or forgetting criterion. MPA and FAA are the respective pass rates, and lambda is the fraction of forgetting criteria. Raw quality is the mean of FAMA = max(0, MPA - lambda * (1 - FAA)) across held-out questions. Retrieved IDs select the answer inputs; they are not scored as a separate retrieval metric.

The final reward applies the fixed task-specific piecewise score mapping documented in `README.md` to raw quality. Raw quality is also reported separately. A confirmed trajectory-audit violation sets the entire reward to zero; an incomplete audit or a failed trusted judge is an infrastructure failure.

## Hidden Test Overview

The held-out questions and reference labels concern the supplied collection and are disjoint from the public validation examples. They are not copied into the Agent-visible environment. Evaluation uses the same input and output contracts, resources and execution limits described above.

## Environment and available resources

Before implementing the system, read the following task-provided documents:

- [`/task/docs/environment.md`](/task/docs/environment.md) — installed runtime, Python packages and system tools.
- [`/task/docs/available_resources.md`](/task/docs/available_resources.md) — available local models or APIs, network restrictions and runtime credential handling.

These documents and the supplied inputs are read-only. Follow the task-specific resource restrictions.

Answers are assessed against the supplied style of answer criteria; prioritize correct, useful answers grounded in the available history.
