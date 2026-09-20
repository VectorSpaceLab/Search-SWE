#!/usr/bin/env python3
"""Run the hidden memory-answer evaluation."""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness import evaluate


def main():
    log = Path("/logs/verifier")
    log.mkdir(parents=True, exist_ok=True)
    (log / "reward.txt").write_text("0\n")
    (log / "reward.json").write_text('{"reward":0}\n')

    required = [
        "ANSWER_API_KEY",
        "ANSWER_API_BASE_URL",
        "ANSWER_MODEL",
        "ANSWER_JUDGE_API_KEY",
        "ANSWER_JUDGE_BASE_URL",
        "ANSWER_JUDGE_MODEL_NAME",
    ]
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        result = {
            "valid": False,
            "score": 0,
            "infrastructure_error": True,
            "error": "Missing verifier settings: " + ", ".join(missing),
        }
        (log / "evaluation.json").write_text(json.dumps(result) + "\n")
        return 1

    result = evaluate(
        "/app",
        "/task/data/history.jsonl",
        "/tests/data/queries.jsonl",
        "/tests/data/golden_answers.jsonl",
        log,
    )
    print(json.dumps({key: value for key, value in result.items() if key != "queries"}))
    return 1 if result.get("infrastructure_error") else 0


if __name__ == "__main__":
    raise SystemExit(main())
