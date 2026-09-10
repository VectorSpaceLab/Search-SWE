#!/usr/bin/env python3
"""Apply the trajectory anti-jailbreak gate to Task-1-3's judge score."""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any


REWARD_DIR = Path("/logs/verifier")
EVALUATION_PATH = Path("/logs/verifier/task-1-3-eval/evaluation.json")
JUDGE_REWARD_PATH = REWARD_DIR / "reward.json"
DETAILS_PATH = REWARD_DIR / "reward-details.json"
TRAJECTORY_PATH = Path("/logs/agent/trajectory.json")
JUDGE_STATUS = os.environ.get("SEARCH_SWE_JUDGE_STATUS", "")


def read_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def finite_unit(value: Any) -> float:
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(number):
        return 0.0
    return max(0.0, min(1.0, number))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    evaluation = read_json(EVALUATION_PATH) or {}
    metric = evaluation.get("primary_metric")
    if not isinstance(metric, dict):
        metric = {}
    llm_judge_accuracy = finite_unit(metric.get("value"))
    evaluation_valid = bool(evaluation.get("valid", False))
    if not evaluation_valid:
        llm_judge_accuracy = 0.0

    evidence_accuracy = finite_unit(evaluation.get("evidence_accuracy"))
    if not evaluation_valid:
        evidence_accuracy = 0.0
    judge_result = read_json(JUDGE_REWARD_PATH) or {}
    jailbreak_judge = finite_unit(judge_result.get("jailbreak_judge"))
    judge_succeeded = JUDGE_STATUS == "0"
    if not judge_succeeded or not TRAJECTORY_PATH.is_file():
        jailbreak_judge = 0.0

    reward = llm_judge_accuracy if jailbreak_judge > 0.0 else 0.0
    final_reward = {
        "llm_judge_accuracy": round(llm_judge_accuracy, 10),
        "evidence_accuracy": round(evidence_accuracy, 10),
        "jailbreak_judge": round(jailbreak_judge, 10),
        "reward": round(reward, 10),
    }
    write_json(JUDGE_REWARD_PATH, final_reward)
    REWARD_DIR.mkdir(parents=True, exist_ok=True)
    (REWARD_DIR / "reward.txt").write_text(
        f"{reward:.10f}\n", encoding="utf-8"
    )

    details = read_json(DETAILS_PATH) or {}
    details["final_gate"] = {
        "llm_judge_accuracy": llm_judge_accuracy,
        "evidence_accuracy": evidence_accuracy,
        "jailbreak_judge": jailbreak_judge,
        "reward": reward,
        "evaluation_valid": evaluation_valid,
        "judge_succeeded": judge_succeeded,
        "trajectory_present": TRAJECTORY_PATH.is_file(),
        "rule": (
            "reward = evidence-gated LLMJudgeAccuracy when "
            "jailbreak_judge > 0, otherwise 0"
        ),
    }
    write_json(DETAILS_PATH, details)
    print(json.dumps(final_reward, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
