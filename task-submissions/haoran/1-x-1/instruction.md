# Task: 1-x-1

## Task Description

Build an executable conversational-memory question-answering system over the supplied meeting transcripts. Given one natural-language question, the system should return one concise answer, drawing on a compact memory library that you build from the transcripts during this task.

The objective is to maximize evidence-grounded answer correctness on held-out questions. You may use any method that satisfies the internal interfaces, the memory and storage budgets, and the resource restrictions.

## Requirements

- Place all submission artifacts under `/app`, which starts empty. Treat `/task` as read-only.
- Submit a finished memory library under `/app/memory/`. Evaluation does not run a memory-construction program. The original transcripts are unavailable to the retrieval and answering programs during evaluation.
- Provide executable `/app/run.sh` and `/app/answerer/answer.sh`. Keep answering code and its static dependencies inside `/app/answerer/`; keep retrieval code, indexes, and the memory under `/app`.
- The memory may retain at most **735,924 bytes** of dialogue — 20% of the dialogue text's 3,679,621 UTF-8 bytes, counting one newline per utterance and excluding JSON metadata. The verifier expands the memory with every container format the runtime can read (xz/lzma, gzip/zlib, bzip2, zstd, lz4, brotli), follows nested containers, and counts what it expands to, so compressing retained dialogue does not buy extra room.
- All submitted files, including memory, indexes, and code, must together fit within **183,981 bytes** on disk. This is separate from the retained-dialogue budget above and is 5% of the same dialogue text. File contents and relative path bytes count once. Links and special files are forbidden.
- Keep scratch files, caches, and experiment output outside `/app`: every submitted file is transferred and counted.
- Memory construction and retrieval must use local computation only. Do not call helper APIs for summarization, memory creation, indexing, embedding, or ranking, including during development. The externally configured coding Agent itself is exempt from this helper-API restriction.
- Read `ANSWER_API_KEY`, `ANSWER_API_BASE_URL`, and `ANSWER_MODEL` from the runtime environment to configure the answering API. The benchmark runner supplies their values at runtime. Only the submitted answerer may use this API, as documented in `/task/docs/available_resources.md`.
- Do not retain uncounted dialogue copies, hard-code public or hidden question-to-answer tables, depend on dataset query IDs, access hidden labels, or modify the evaluator.
- Complete implementation and validation within 120 minutes.

### Stage 1: retrieval

The verifier invokes the following command once per question, with networking disabled and no API credentials:

```bash
/app/run.sh \
  --memory-dir /app/memory \
  --question "$question" \
  --output /path/to/memories.json
```

`--question` is the natural-language question itself, passed as one argument, without an ID or meeting metadata. Write a JSON array of at most ten retrieved records in relevance order to the output file. Each record must have nonempty string `id` and `text` fields, with distinct IDs within the result. Additional metadata is allowed. Records must come from the submitted memory; its internal storage format is your choice. Submission files are read-only; use the supplied output directory for runtime scratch files.

### Stage 2: answering

After collecting the retrieval output, the verifier invokes:

```bash
/app/answerer/answer.sh \
  --question "$question" \
  --memories /path/to/memories.json \
  --output /path/to/answer.txt
```

`--question` is the same question text. `--memories` points to a read-only JSON file containing exactly the list from Stage 1; it contains no reference evidence or answer. Use the supplied paths, which may vary between invocations. Write only the final UTF-8 answer to the output file. Both scripts must exit with status `0`.

Each answering process starts fresh and can read only this question's recalled records, its own corpus-independent code, and runtime dependencies. It cannot read the full memory, original transcripts, other questions or previous answers. All network access is disabled except calls to the configured answering model through the task-provided API transport. Implement the answering prompts and response handling in your submission.

### Output contract

For every request the system receives one natural-language question and returns one plain-text answer:

- the answer must be a nonempty UTF-8 string of at most **2,000 Unicode characters**;
- it must not contain recalled records, citations, or memory identifiers;
- if the evidence is insufficient, the answer should say so in plain text.

## Available Validation Data

The following files are available in the task environment:

- `/task/data/history.jsonl` — the complete transcripts, with `meeting_id`, `series_id`, `date`, `speaker`, `start_seconds`, `end_seconds`, `text`, and `source_ids`. A null speaker is unidentified. Speech offsets locate an utterance within a meeting.
- `/task/data/validation/queries.jsonl` — 30 public development questions. Each row includes bookkeeping fields for analysis, but the runtime interface supplies only the natural-language question.
- `/task/data/validation/golden_answers.jsonl` — public reference answers and required factual points, keyed by `query_id`.
- `/task/data/validation/evidence.jsonl` — transcript excerpts supporting the public reference answers.

Use these files to develop and check the system. Hidden questions concern the same transcripts and are disjoint from the public questions.

Before submitting, check both size budgets and run the two entry points on the public questions. Use the development API route documented in `/task/docs/available_resources.md` when testing the answerer.

## Expected Artifacts

The finalized submission must contain an executable `/app/run.sh`, an executable `/app/answerer/answer.sh`, the finished memory under `/app/memory/`, and whatever code they need.

```text
/app/
├── memory/               # finished compact memory and indexes
├── run.sh                # executable retrieval entry point
├── answerer/
│   ├── answer.sh         # executable answering entry point
│   └── ...               # corpus-independent answering code and dependencies
└── ...                   # other retrieval code and dependencies
```

## Verification

After the Agent phase, Harbor transfers `/app` to a separate verifier with the same runtime and the private question set. The verifier checks the following items:

1. **Memory and retrieval integrity.** The submission must answer from the supplied transcripts through the memory it submits. It must not keep uncounted copies of the dialogue, obtain answers or judgments from hidden labels, hard-code question-to-answer or question-to-result tables, serve a fixed answer file instead of running the submitted answerer, or reach any service other than the configured answering API.
2. **Resource compliance.** Follow `/task/docs/available_resources.md`. The retained-dialogue and disk budgets above are enforced by measurement, not by declaration, and no helper API may be used for memory construction, indexing, embedding, retrieval, or ranking.
3. **Executable and output validity.** Both entry points must exist and be executable, run with read-only submission files, and honour the two interfaces above. Retrieval has a combined 150-second budget for a full question set and answering a combined 1,800-second budget, with at most two answering API calls per question and at most 2,000 output tokens per call. Invalid output or a failed executable gate receives a score of `0`.
4. **Evidence hit.** The retrieved texts are compared with annotated transcript evidence for the question. A hit requires at least one question-relevant factual point from the supporting excerpts to be preserved; faithful summaries and paraphrases count. Topic overlap, matching keywords or a claimed evidence ID alone do not count.
5. **Answer correctness.** A separate LLM judgment compares the final answer with the reference answer and required facts. Missing required facts, contradictions and unanswered questions are incorrect; paraphrases are accepted. The evidence judgment does not see the submitted answer, and the answer judgment does not see the retrieved records.

The verifier saves both stages' outputs before grading. Each question scores one only if the retrieved evidence is a hit **and** the answer is correct. It also reports evidence-hit rate and answer accuracy separately. The final metric is EvidenceGroundedAnswerAccuracy:

```text
score = 100 * mean(evidence_hit AND answer_correct)
```

An independent trajectory audit checks compliance with the task and resource restrictions. A confirmed violation sets the entire submission's score to `0`.

## Hidden Test Overview

The hidden evaluation contains 118 held-out questions over the same 67 meetings, with private reference answers and supporting transcript evidence. The hidden questions are disjoint from the public development examples and are not copied into the Agent-visible environment. At evaluation time each program receives only the inputs documented above.

## Environment and available resources

Before implementing the system, read the following task-provided documents:

- [`/task/docs/environment.md`](/task/docs/environment.md) — the installed Python environment, system runtime, and resource limits.
- [`/task/docs/available_resources.md`](/task/docs/available_resources.md) — the answering API resources, runtime credential handling, model and endpoint restrictions, and jailbreak penalty rules.

These documents are part of the Agent-visible task data and should be treated as read-only. Follow the resource and model restrictions in `available_resources.md`; do not infer permission to use an unlisted provider, model, or endpoint. Credentials are injected by Harbor at runtime and must not be placed in the task package or Docker image.
