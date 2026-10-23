# Compact Conversational Memory Question Answering

## Task Description

Build a system for asking questions about past meetings without keeping the full transcripts in the answering system. Prepare a compact memory and an executable search-and-answer pipeline: build an index from that memory, retrieve the relevant notes for a question, and use those notes to produce a concise answer. The goal is to maximize evidence-grounded answer correctness on held-out questions. You may choose the memory structure, index and retrieval method within the interfaces and limits below.

## Requirements

### Resource limits

- You have 120 minutes for implementation and validation, with eight CPU cores, 8 GiB RAM, 8 GiB storage and no GPU.
- Development runs as root, and no local model weights are supplied under `/opt/models`.
- Treat `/task` and its documentation as read-only.
- Do not obtain held-out labels, change the evaluator, use external answer services or embed answers to particular evaluation questions.

### Memory file

The memory must be readable UTF-8 JSON, with no duplicate object keys or non-finite numbers, and no larger than 183,981 bytes. This is five percent of the history's 3,679,621 UTF-8 dialogue-text bytes, including one newline per utterance and excluding the source JSON metadata. The limit counts the actual bytes of `memory.json`, including its formatting and metadata. Choose its JSON structure freely, but store directly readable memory text rather than compressed or encoded dialogue. Script bytes and the index generated from this memory are outside that memory-file budget.

### Execution and file permissions

- Honor every supplied path, which may vary between invocations, and return exit status `0` from all three scripts.
- Submitted commands run as a non-root user in a fresh working directory for each invocation.
- Submitted files, stage inputs and installed runtime files are read-only; only that stage's working directory is writable.
- Hidden evaluation files, grading outputs and judge credentials are inaccessible to the submitted programs.
- The stage budgets sit within a 5,400-second overall verifier phase and do not extend it.

### Build interface

To prepare the memory for repeated questions, provide the build interface:

```bash
/app/build.sh \
  --memory /app/memory.json \
  --output /path/to/index
```

It runs once and has 300 seconds, including Jina calls. Create the requested index directory, which does not initially exist; its parent exists and is writable for temporary work. This stage can read `memory.json`, `build.sh`, the supplied Jina transport and installed runtime dependencies, but not the other scripts, original transcripts or evaluation data. Only the resulting index is retained for retrieval, and it becomes read-only. Its entries must be regular files or directories without links.

### Search interface and output contract

For each question, the search interface is:

```bash
/app/run.sh \
  --index /path/to/index \
  --question "$question" \
  --output /path/to/memories.json
```

Write a JSON array of at most ten strings in relevance order, drawn from the indexed memory; an empty array is allowed. Search can read only the index, `run.sh`, the supplied Jina transport and installed runtime dependencies. It cannot read `memory.json`, other scripts, the original transcripts or other requests. Use the output file's parent for temporary work. All searches together have 150 seconds, including Jina calls.

### Answer interface and output contract

For each search result, the answering interface is:

```bash
/app/answer.sh \
  --question "$question" \
  --memories /path/to/memories.json \
  --output /path/to/answer.txt
```

Its memories file contains exactly the string array returned by search. The answerer may read only `answer.sh`, this question's recalled strings, the supplied generation transport and installed runtime dependencies. It cannot consult the full memory, index, other scripts, original transcripts or previous requests. Write nonempty UTF-8 answer text of at most 2,000 Unicode characters, without a JSON wrapper or a list of recalled notes. If the notes are insufficient, say so in plain text. All answers together have 1,800 seconds; use the output file's parent for temporary work.

## Available Validation Data

The complete history is available at `/task/data/history.jsonl`. Its records contain `meeting_id`, `series_id`, `date`, `speaker`, `start_seconds`, `end_seconds`, `text` and `source_ids`; a null speaker is unidentified. To check the system while developing it, use the five public questions at `/task/data/validation/queries.jsonl`, the reference answers and required facts at `/task/data/validation/golden_answers.jsonl`, and their supporting transcript excerpts at `/task/data/validation/evidence.jsonl`. The reference files are keyed by `query_id`, but the program receives only each row's `question` as a single command-line argument, without an ID or meeting metadata. The remaining public-query fields are for analysis. The final questions concern the same 67 meetings, so prepare the memory from the supplied history rather than from a list of question-to-answer mappings.

Check the memory's JSON validity and byte size, then run build, search and answer on the public questions using the development API route where needed.

## Expected Artifacts

Deliver exactly four regular files under `/app`: the finished `memory.json` and executable `build.sh`, `run.sh` and `answer.sh` scripts. Links are not supported. Each script must be self-contained, using embedded code or installed libraries rather than additional submitted modules. The scripts must contain corpus-independent implementation code, without additional memories, transcript excerpts or question-to-answer tables. Keep other development outputs outside `/app`. Only these four files are transferred to the separate evaluation environment; files in your home directory, additional installed packages, indexes and running services are not transferred.

```text
/app/
├── memory.json
├── build.sh
├── run.sh
└── answer.sh
```

## Verification

After you finish, Harbor transfers the four files to a separate verifier and runs the same interfaces on 143 held-out questions.

A failed process, invalid submission or invalid output receives zero for the submission.

An answer earns credit only when both its retrieved evidence and its answer are correct. The retrieved notes must preserve at least one question-relevant factual point from the supporting excerpts; faithful summaries and paraphrases count, while topic overlap alone does not. The answer must agree with the reference and include the required facts without contradictions. Evidence is judged without seeing the submitted answer, and the answer is judged without seeing the retrieved notes. EvidenceGroundedAnswerAccuracy is the mean of these joint binary outcomes, and the final reward applies the fixed task-specific piecewise normalization documented in README.md to that mean. A separate trajectory and file audit checks task and resource compliance; a violation sets the entire score to zero, while an incomplete audit or a failed judge service is an infrastructure failure.

## Hidden Test Overview

The held-out questions, reference answers and evidence are disjoint from the public examples and are not provided in the development environment.

## Environment and available resources

Before implementing the system, read the following task-provided documents:

- [`/task/docs/environment.md`](/task/docs/environment.md) — installed runtime, Python packages and system tools.
- [`/task/docs/available_resources.md`](/task/docs/available_resources.md) — available local models or APIs, network restrictions and runtime credential handling.

These documents and the supplied inputs are read-only. Follow the task-specific resource restrictions.

Local computation and the supplied Jina embedding and reranking APIs are available for memory preparation, indexing and retrieval. Generative helper APIs are not permitted for those operations. Only the answering component may use the OpenRouter generation API, with the current question and retrieved strings, choosing among the four models in the resource policy. An unlisted model, provider or endpoint is not authorized. Harbor supplies the documented credentials at runtime; do not put their values in code, memories, indexes, prompts or logs.

### Retrieval API transport

For Jina calls during evaluation, `build.sh` and `run.sh` receive `TASK_JINA_CLIENT` and `TASK_JINA_FD`. Load the supplied client module and use its `embeddings` or `rerank` function, preserving the named file descriptor when starting a subprocess. The client forwards the operation and provider request body while the real key stays outside the submitted process; direct network access is disabled. Each serialized request, including its newline, must fit within 128 KiB, so batch larger inputs. There is no separate Jina call-count limit, but calls consume the current stage's time budget. Use only the permitted stage inputs. During development, when this transport is absent, use the documented Jina endpoints with `JINA_API_KEY` and text from the supplied history. The answerer does not receive the Jina transport.

### Answer API transport

For generation during evaluation, `answer.sh` receives `TASK_LLM_CLIENT` and `TASK_LLM_FD`. Load that client module and call `chat_completion`, preserving its file descriptor across subprocesses. When the client is present, use it without requiring `OPENROUTER_API_KEY` or direct network access. During development the transport is absent, and the answerer may send the same request to the documented OpenRouter Chat Completions endpoint using `OPENROUTER_API_KEY`. The resource policy includes examples of both routes. Each request must explicitly select an allowed model and use only the current question and retrieved notes; a failed call does not permit another provider or endpoint.

Each question allows at most two generation calls, with 1–2,000 output tokens per call. The accepted request options are `model`, `messages`, `temperature`, `top_p`, `max_tokens` and `response_format`. A request may contain 1–32 messages, each with exactly the string fields `role` and `content`; roles may be `system`, `user` or `assistant`. The serialized request, including its newline, must fit within 128 KiB. Streaming, tool calls and alternate endpoints are not supported.
