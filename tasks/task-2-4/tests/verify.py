#!/usr/bin/env python3
"""Run Task-2-4 and write its Gold Recall@5 as the Harbor reward."""

from __future__ import annotations

import json
import math
import subprocess
import sys
from pathlib import Path


REWARD_DIR = Path("/logs/verifier")
RESULTS_DIR = REWARD_DIR / "task-2-4-eval"
REPORT_PATH = RESULTS_DIR / "evaluation.json"


def bounded(value: object) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, number if math.isfinite(number) else 0.0))


def write_reward(report: dict) -> float:
    metric = report.get("primary_metric", {}) if report.get("valid") else {}
    reward = bounded(metric.get("value", 0.0)) if metric.get("name") == "GoldRecall@5" else 0.0
    verifier = REWARD_DIR
    verifier.mkdir(parents=True, exist_ok=True)
    (verifier / "reward.txt").write_text(f"{reward:.10f}\n", encoding="utf-8")
    (verifier / "reward.json").write_text(
        json.dumps(
            {
                "gold_recall_at_5": reward,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return reward


def main() -> int:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.unlink(missing_ok=True)
    command = [
        sys.executable,
        "/tests/run_submission.py",
        "--submission-dir", "/app",
        "--corpus", "/task/data/corpus.jsonl",
        "--queries", "/tests/data/queries.jsonl",
        "--qrels", "/tests/data/qrels_gold.txt",
        "--results-dir", str(RESULTS_DIR),
        "--evaluator", "/tests/evaluate.py",
        "--build-timeout", "600",
        "--score-timeout", "120",
        "--query-concurrency", "5",
    ]
    try:
        # One shared execution budget; queries have no individual timeout.
        completed = subprocess.run(command, check=False, timeout=15300)
    except Exception as error:
        REPORT_PATH.write_text(
            json.dumps({"valid": False, "score": 0.0, "errors": [str(error)]}) + "\n",
            encoding="utf-8",
        )
        completed = None
    try:
        report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        report = {}
    reward = write_reward(report)
    print(json.dumps({"submission_returncode": completed.returncode if completed else None, "reward": reward}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
