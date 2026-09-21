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

Memory preparation, index construction and retrieval must use local computation only. Do not call helper APIs for these operations, including during development. The externally configured coding Agent itself is exempt from this helper-API restriction. Only the submitted answerer may use the OpenRouter generation API, with the current question and retrieved strings. It may choose any of the four model IDs listed in the resource policy. Read `/task/docs/available_resources.md` for credentials and the model allowlist.

Treat `/task` as read-only. Do not access held-out labels, modify the evaluator or embed answers to particular evaluation questions. Complete implementation and validation within 120 minutes.

The container provides 8 CPUs, 8 GiB RAM, 8 GiB storage and no GPU. Development runs as root, with numerical libraries defaulting to one thread per process. No local model weights are supplied under `/opt/models`. Network access follows the resource policy.

### Build interface

The verifier first runs:

```bash
/app/build_index.sh \
  --memory /app/memory.json \
  --output /path/to/index
```

Create the requested index directory and write the index there. The directory does not exist initially; its parent exists and is writable. This phase runs once, offline, with a 300-second timeout. It can read `memory.json`, `build_index.sh` and installed runtime dependencies. It cannot read the other submitted scripts, original transcripts or evaluation data. Use the output directory's parent for temporary work. Only the index directory is retained for retrieval; its contents become read-only. Index entries must be regular files or directories, without links. The index's runtime size is not part of the submitted-memory budget.

### Search interface

For each question, the verifier runs:

```bash
/app/search.sh \
  --index /path/to/index \
  --question "$question" \
  --output /path/to/memories.json
```

Retrieval runs offline and can read only the index, `search.sh` and installed runtime dependencies. It cannot read `memory.json`, other scripts, original transcripts or other requests. Use the output file's parent for temporary work. Retrieval has a combined 150-second budget for the question set.

The verifier then runs:

```bash
/app/answer.sh \
  --question "$question" \
  --memories /path/to/memories.json \
  --output /path/to/answer.txt
```

Answering can read only `answer.sh`, the current recalled strings, the task-provided API transport and installed runtime dependencies. The question is provided through the argument above. It cannot read the full memory, index, other scripts, original transcripts or previous requests. It may call only the allowed OpenRouter models through the provided transport; other network access is disabled. The transport holds the real API credential outside the submitted process.

Answering has a combined 1,800-second budget. Use the output file's parent for temporary work.

All three scripts must honour the supplied paths, which can vary between invocations, and exit with status `0`. Each process starts with a fresh working directory. Submitted files, stage inputs and installed runtime files are read-only; only the current stage's working directory is writable. Hidden evaluation files, judge credentials and grading outputs are inaccessible to all submitted programs.

During evaluation, `answer.sh` receives `TASK_LLM_CLIENT` and `TASK_LLM_FD`. The provided client forwards Chat Completions requests while the verifier retains the real provider credential. Direct network access from the submitted process is disabled.

```python
import importlib.util
import os

spec = importlib.util.spec_from_file_location("task_llm", os.environ["TASK_LLM_CLIENT"])
api = importlib.util.module_from_spec(spec)
spec.loader.exec_module(api)
response = api.chat_completion(
    messages=[{"role": "user", "content": prompt_from_current_query_and_retrieved_memories}],
    model="qwen/qwen3.5-9b",  # Example; choose any model from the allowlist.
    temperature=0,
    max_tokens=1000,
)
text = response["choices"][0]["message"]["content"]
```

Preserve the file descriptor named by `TASK_LLM_FD` when starting an answerer subprocess. When `TASK_LLM_CLIENT` is present, use this transport and do not require `OPENROUTER_API_KEY`.

The development container provides `OPENROUTER_API_KEY` but no evaluation transport. When `TASK_LLM_CLIENT` is absent, your answerer may send the same request directly to the configured API:

```python
import os
import requests

response = requests.post(
    "https://openrouter.ai/api/v1/chat/completions",
    headers={"Authorization": "Bearer " + os.environ["OPENROUTER_API_KEY"]},
    json=request_body,
    timeout=45,
    allow_redirects=False,
)
response.raise_for_status()
result = response.json()
```

Build `request_body` from the current question and your retriever's output, including an explicit allowed `model`. The same API limits apply in development and evaluation. A failed call does not permit using an unlisted model, provider or endpoint.

### Output contract

Write a JSON array containing at most ten strings, in relevance order. An empty array is allowed. The question is passed as one argument, without a query ID or meeting metadata. Retrieved strings must be drawn from the indexed memory.

The memories file contains exactly the string array from retrieval. Write the final answer as nonempty UTF-8 text of at most **2,000 Unicode characters**, without a JSON wrapper or recalled-memory listing. If the retrieved information is insufficient, say so in plain text.

Each question permits at most two API calls, with at most 2,000 output tokens per call. Allowed request options are `model`, `messages`, `temperature`, `top_p`, `max_tokens`, and `response_format`. Only the listed request options are accepted by the evaluation transport.

A request may contain 1–32 messages with string `role` and `content` fields; permitted roles are `system`, `user` and `assistant`. The serialized request, including its newline, must fit within 128 KiB. Streaming, tool calls and alternate endpoints are not supported. If the retrieved information is insufficient, answer accordingly rather than seeking other evidence.

## Available Validation Data

The following files are available during development:

- `/task/data/history.jsonl`: complete transcripts, with `meeting_id`, `series_id`, `date`, `speaker`, `start_seconds`, `end_seconds`, `text` and `source_ids`. A null speaker is unidentified.
- `/task/data/validation/queries.jsonl`: 30 development questions; use each row's `question` as the script argument. Other fields are for analysis only.
- `/task/data/validation/golden_answers.jsonl`: reference answers and required facts, keyed by `query_id`.
- `/task/data/validation/evidence.jsonl`: transcript excerpts supporting those answers.

Check the JSON format and size, then run the three commands above on the public questions. Use the development API route described in the search interface above. Held-out questions concern the same transcripts and are disjoint from these examples.

## Expected Artifacts

Only these four submission files are transferred to the separate evaluation environment. Files in the development home directory, extra installed packages and running services are not transferred. Make all three scripts executable. The index is generated during evaluation and is not a submitted artifact.

```text
/app/
├── memory.json
├── build_index.sh
├── search.sh
└── answer.sh
```

## Verification

After implementation, Harbor transfers the four files into a separate verifier with the held-out question set. The verifier checks:

1. **Retrieval and answer integrity.** Use the supplied history to prepare the memory. Do not access held-out labels, place additional corpus-specific memories or answer tables in scripts, or bypass the required retrieval and answering pipeline.
2. **Resource compliance.** Follow `/task/docs/available_resources.md`. The memory budget is 183,981 bytes. Index construction has 300 seconds; retrieval and answering have combined budgets of 150 and 1,800 seconds respectively, within a 5,400-second verifier phase.
3. **Executable and output validity.** The four files, script permissions, JSON validity, index construction, process completion and output formats must satisfy the contract. A failed process or invalid submission receives zero.
4. **Final answer score.** Each question scores one only when both retrieved evidence and answer correctness pass. Retrieved strings must preserve at least one question-relevant factual point from the supporting excerpts; faithful summaries and paraphrases count, topic overlap alone does not. A separate answer judge compares the answer with the reference and required facts; missing required facts or contradictions are incorrect. The evidence judge does not see the submitted answer, and the answer judge does not see the retrieved strings.

```text
EvidenceGroundedAnswerAccuracy(q) = 1 if evidence_hit AND answer_correct, else 0
reward = mean_q EvidenceGroundedAnswerAccuracy(q)
score = 100 * reward
```

An independent trajectory and file audit checks compliance with the task and resource restrictions. A violation sets the entire reward and score to zero; an incomplete audit is an infrastructure failure.

## Hidden Test Overview

Evaluation uses 118 held-out questions over the same 67 meetings. The questions, reference answers and supporting evidence are not supplied to the development environment. Each submitted program receives only its documented inputs during evaluation.

## Environment and available resources

Before implementing the system, read:

- [`/task/docs/environment.md`](/task/docs/environment.md): installed Python environment, runtime and tools.
- [`/task/docs/available_resources.md`](/task/docs/available_resources.md): answering API configuration, model and endpoint restrictions, and usage rules.

These read-only documents are part of the task data. Follow their restrictions. The benchmark runner configures API access at runtime; credentials must not be placed in submitted files.
