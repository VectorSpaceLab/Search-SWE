#!/usr/bin/env python3
"""Apply the trajectory anti-jailbreak gate to Task-1-4's Recall@5."""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any


REWARD_DIR = Path("/logs/verifier")
EVALUATION_PATH = Path("/logs/verifier/task-1-4-eval/evaluation.json")
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
    primary_metric = evaluation.get("primary_metric")
    if not isinstance(primary_metric, dict):
        primary_metric = {}
    recall_at_5 = finite_unit(primary_metric.get("value"))
    evaluation_valid = bool(evaluation.get("valid", False))
    if not evaluation_valid:
        recall_at_5 = 0.0

    judge_result = read_json(JUDGE_REWARD_PATH) or {}
    jailbreak_judge = finite_unit(judge_result.get("jailbreak_judge"))
    judge_succeeded = JUDGE_STATUS == "0"
    trajectory_present = (
        TRAJECTORY_PATH.is_file() and not TRAJECTORY_PATH.is_symlink()
    )
    if not judge_succeeded or not trajectory_present:
        jailbreak_judge = 0.0

    reward = recall_at_5 if jailbreak_judge > 0.0 else 0.0
    final_reward = {
        "recall_at_5": round(recall_at_5, 10),
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
        "recall_at_5": recall_at_5,
        "jailbreak_judge": jailbreak_judge,
        "reward": reward,
        "evaluation_valid": evaluation_valid,
        "judge_succeeded": judge_succeeded,
        "trajectory_present": trajectory_present,
        "rule": (
            "reward = Recall@5 when evaluation is valid and "
            "jailbreak_judge > 0, otherwise 0"
        ),
    }
    write_json(DETAILS_PATH, details)
    print(json.dumps(final_reward, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
