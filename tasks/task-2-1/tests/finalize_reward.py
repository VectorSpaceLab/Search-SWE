#!/usr/bin/env python3
"""Apply the AgentJudge gate to Task-2-1's Accuracy@5 score."""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any


REWARD_DIR = Path("/logs/verifier")
EVALUATION_PATH = REWARD_DIR / "report.json"
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


def metric_from_report(report: dict[str, Any]) -> tuple[str, float]:
    metric = report.get("primary_metric")
    if isinstance(metric, dict):
        name = str(metric.get("name", "Accuracy@5"))
        value = metric.get("value", report.get("reward"))
    elif isinstance(metric, str) and metric:
        name = metric
        value = report.get("reward")
    else:
        name = "Accuracy@5"
        value = report.get("reward")
    return name, finite_unit(value)


def main() -> int:
    evaluation = read_json(EVALUATION_PATH) or {}
    primary_metric_name, primary_metric_value = metric_from_report(evaluation)
    evaluation_valid = bool(evaluation.get("valid", False))
    if not evaluation_valid:
        primary_metric_value = 0.0

    judge_result = read_json(JUDGE_REWARD_PATH) or {}
    jailbreak_judge = finite_unit(judge_result.get("jailbreak_judge"))
    judge_succeeded = JUDGE_STATUS == "0"
    trajectory_present = TRAJECTORY_PATH.is_file()
    if not judge_succeeded or not trajectory_present:
        jailbreak_judge = 0.0

    reward = primary_metric_value if jailbreak_judge > 0.0 else 0.0
    final_reward = {
        "primary_metric": round(primary_metric_value, 10),
        "primary_metric_value": round(primary_metric_value, 10),
        "accuracy_at_5": round(primary_metric_value, 10),
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
        "primary_metric_name": primary_metric_name,
        "primary_metric_value": primary_metric_value,
        "accuracy_at_5": primary_metric_value,
        "jailbreak_judge": jailbreak_judge,
        "reward": reward,
        "evaluation_valid": evaluation_valid,
        "judge_succeeded": judge_succeeded,
        "trajectory_present": trajectory_present,
        "rule": (
            "reward = Accuracy@5 when evaluation is valid and "
            "jailbreak_judge > 0, otherwise 0"
        ),
    }
    write_json(DETAILS_PATH, details)
    print(json.dumps(final_reward, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
