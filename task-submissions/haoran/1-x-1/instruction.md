# Task: 1-x-1

## Task Description

Build a conversational-memory question-answering system over the supplied meeting transcripts. Prepare a memory, an index builder, a retriever and an answerer. Given a natural-language question, the system should return a concise answer using the memories it retrieves.

The objective is to maximize evidence-grounded answer correctness on held-out questions.

## Requirements

Submit exactly four files under `/app`:

- `memory.json`: your finished memory, stored as readable UTF-8 JSON.
- `build_index.sh`: an executable script that builds an index from the memory.
- `search.sh`: an executable script that retrieves up to ten strings from the index for a question.
- `answer.sh`: an executable script that answers the question using those strings.

`memory.json` must be valid JSON, with no duplicate object keys or non-finite numbers, and no larger than **183,981 bytes**. This is 5% of the supplied dialogue text's 3,679,621 UTF-8 bytes, including one newline per utterance and excluding JSON metadata. Choose your own JSON structure; its memory content must be directly readable text, not compressed or encoded dialogue. The budget counts only the actual bytes of `memory.json`, including its formatting and metadata.

The scripts are not included in that memory budget. They must contain corpus-independent implementation code, not additional memories, transcript excerpts or question-to-answer tables. Each script must be self-contained: it may embed Python or use installed libraries, but may not depend on extra submitted files. Files must be regular files; links are not supported. Keep development outputs outside `/app`.

Memory preparation, index construction and retrieval must use local computation only. Do not call helper APIs for these operations, including during development. The externally configured coding Agent itself is exempt from this helper-API restriction. Only the submitted answerer may use the configured generation API, with the current question and retrieved strings. Read `/task/docs/available_resources.md` for its configuration and transport.

Treat `/task` as read-only. Do not access held-out labels, modify the evaluator or embed answers to particular evaluation questions. Complete implementation and validation within 120 minutes.

### Index construction

The verifier first runs:

```bash
/app/build_index.sh \
  --memory /app/memory.json \
  --output /path/to/index
```

Create the requested index directory and write the index there. The directory does not exist initially; its parent exists and is writable. This phase runs once, offline, with a 300-second timeout. It can read `memory.json`, `build_index.sh` and installed runtime dependencies. It cannot read the other submitted scripts, original transcripts or evaluation data. Use the output directory's parent for temporary work. Only the index directory is retained for retrieval; its contents become read-only. Index entries must be regular files or directories, without links. The index's runtime size is not part of the submitted-memory budget.

### Retrieval

For each question, the verifier runs:

```bash
/app/search.sh \
  --index /path/to/index \
  --question "$question" \
  --output /path/to/memories.json
```

Write a JSON array containing at most ten strings, in relevance order. An empty array is allowed. The question is passed as one argument, without a query ID or meeting metadata. Retrieved strings must be drawn from the indexed memory.

Retrieval runs offline and can read only the index, `search.sh` and installed runtime dependencies. It cannot read `memory.json`, other scripts, original transcripts or other requests. Use the output file's parent for temporary work. Retrieval has a combined 150-second budget for the question set.

### Answering

The verifier then runs:

```bash
/app/answer.sh \
  --question "$question" \
  --memories /path/to/memories.json \
  --output /path/to/answer.txt
```

The memories file contains exactly the string array from retrieval. Write the final answer as nonempty UTF-8 text of at most **2,000 Unicode characters**, without a JSON wrapper or recalled-memory listing. If the retrieved information is insufficient, say so in plain text.

Answering can read only `answer.sh`, the current recalled strings, the task-provided API transport and installed runtime dependencies. The question is provided through the argument above. It cannot read the full memory, index, other scripts, original transcripts or previous requests. It may call only the configured LLM through the provided transport; other network access is disabled. The transport holds the real API credential outside the submitted process.

Answering has a combined 1,800-second budget, with at most two API calls per question and 2,000 output tokens per call. Use the output file's parent for temporary work.

All three scripts must honour the supplied paths, which can vary between invocations, and exit with status `0`. Each process starts with a fresh working directory. Submitted files, stage inputs and installed runtime files are read-only; only the current stage's working directory is writable. Hidden evaluation files, judge credentials and grading outputs are inaccessible to all submitted programs.

## Available Validation Data

The following files are available during development:

- `/task/data/history.jsonl`: complete transcripts, with `meeting_id`, `series_id`, `date`, `speaker`, `start_seconds`, `end_seconds`, `text` and `source_ids`. A null speaker is unidentified.
- `/task/data/validation/queries.jsonl`: 30 development questions; use each row's `question` as the script argument. Other fields are for analysis only.
- `/task/data/validation/golden_answers.jsonl`: reference answers and required facts, keyed by `query_id`.
- `/task/data/validation/evidence.jsonl`: transcript excerpts supporting those answers.

Check the JSON format and size, then run the three commands above on the public questions. Use the development answering-API route documented in `/task/docs/available_resources.md`. Held-out questions concern the same transcripts and are disjoint from these examples.

## Expected Artifacts

```text
/app/
├── memory.json
├── build_index.sh
├── search.sh
└── answer.sh
```

Only these four submission files are transferred to the separate evaluation environment. Make all three scripts executable. The index is generated during evaluation and is not a submitted artifact.

## Verification

After implementation, Harbor transfers the four files into a separate verifier and uses the held-out question set. The verifier checks:

1. **Submission and interface validity.** The four required files, script permissions, JSON validity, memory size, index construction, process completion and output formats must satisfy the contract. An invalid submission receives zero.
2. **Compliance.** An independent trajectory and file audit checks use of the provided data, API resources and stage interfaces. Accessing evaluation labels, supplying hidden extra memories in code, altering evaluation results or otherwise bypassing the required pipeline is a violation and sets the score to zero.
3. **Retrieved evidence.** The strings are compared with supporting transcript excerpts. A hit requires at least one question-relevant factual point to be preserved. Faithful summaries and paraphrases count; topic overlap alone does not.
4. **Answer correctness.** A separate LLM judgment compares the answer with the reference and required facts. Missing required facts or contradictory claims are incorrect; paraphrases are accepted. This judgment does not see the retrieved strings, and the evidence judgment does not see the submitted answer.

Both outputs are saved before grading. Each question scores one only if both evidence and answer checks pass. The final metric is EvidenceGroundedAnswerAccuracy:

```text
score = 100 * mean(evidence_hit AND answer_correct)
```

## Hidden Test Overview

Evaluation uses 118 held-out questions over the same 67 meetings. The questions, reference answers and supporting evidence are not supplied to the development environment. Each submitted program receives only its documented inputs during evaluation.

## Environment and available resources

Before implementing the system, read:

- [`/task/docs/environment.md`](/task/docs/environment.md): installed Python environment, runtime and tools.
- [`/task/docs/available_resources.md`](/task/docs/available_resources.md): answering API configuration, model and endpoint restrictions, and usage rules.

These read-only documents are part of the task data. Follow their restrictions. The benchmark runner configures API access at runtime; credentials must not be placed in submitted files.
