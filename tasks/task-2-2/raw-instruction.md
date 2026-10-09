# Task: Task-2-2

## Task Description

Improve the supplied code-retrieval embedder using the provided corpus and training data. The submitted checkpoint is evaluated with exact Top-1 retrieval on held-out queries.

## Requirements

- Treat /task as read-only and write the final checkpoint to /app/submission/model.
- The Agent phase has a 12-hour time limit. Task-specific submission verification has a 1-hour time limit, excluding the separate integrity judge. If the Agent phase, task-specific verification, or integrity judge times out, the score is 0.
- Start from the backbone at /task/models/bge-base-en-v1.5.
- Preserve the backbone architecture, parameter names, parameter shapes, and parameter count.
- Produce a self-contained checkpoint that AutoTokenizer.from_pretrained and AutoModel.from_pretrained can load with local_files_only=True.
- Do not use hidden data, hard-coded query-to-document mappings, precomputed answers, or external resources.
- Network access is unavailable.

## Available Validation Data

The corpus and training data are under /task/data. A fixed 10-query public validation split and its labels are under /task/data/validation.

## Environment and Available Resources

Read /task/docs/environment.md and /task/docs/available_resources.md. The supplied backbone is mounted read-only under /task/models.

## Expected Artifacts

Submit a complete offline checkpoint:

~~~text
/app/submission/
└── model/
~~~

The verifier ignores files outside /app/submission.

## Verification

The verifier copies the checkpoint into a separate environment, confirms that it preserves the supplied backbone architecture, and evaluates the original and submitted checkpoints with the same fixed embedding and exact-search implementation. Larger held-out Accuracy@1 improvement is better.

## Hidden Test Overview

The hidden split contains code-retrieval queries and private relevance labels disjoint from the public validation split. Hidden data is unavailable during the Agent phase.
