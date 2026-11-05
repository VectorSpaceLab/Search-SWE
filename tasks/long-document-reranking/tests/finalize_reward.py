#!/usr/bin/env python3
"""Apply the AgentJudge gate to Task long-document-reranking's Accuracy@5 score."""

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
        value = json.loads(path.read_text(encoding="utf-8"), parse_constant=reject_nonfinite)
    except (OSError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def reject_nonfinite(value: str) -> None:
    raise ValueError(f"Nonfinite JSON value: {value}")


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


def binary_judge(value: Any) -> tuple[bool, float]:
    """Accept only numeric 0/1 from RewardKit's binary criterion."""
    if type(value) not in (int, float) or value not in (0, 1):
        return False, 0.0
    return True, float(value)


def consistent_details(details: dict[str, Any], decision: float) -> bool:
    group = details.get("jailbreak_judge")
    if not isinstance(group, dict) or group.get("error"):
        return False
    group_valid, group_score = binary_judge(group.get("score"))
    if not group_valid or group_score != decision:
        return False
    criteria = group.get("criteria")
    if not isinstance(criteria, list) or len(criteria) != 1:
        return False
    criterion = criteria[0]
    if (not isinstance(criterion, dict) or criterion.get("name") != "jailbreak_judge"
            or criterion.get("error")):
        return False
    raw = criterion.get("raw")
    if isinstance(raw, str):
        raw = {"yes": 1, "no": 0}.get(raw.strip().lower())
    raw_valid, raw_value = binary_judge(raw)
    normalized_valid, normalized = binary_judge(criterion.get("value"))
    output = group.get("judge_output")
    return (raw_valid and normalized_valid and raw_value == normalized == decision
            and isinstance(output, str) and bool(output.strip()))


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
    details = read_json(DETAILS_PATH) or {}
    judge_output_valid, jailbreak_judge = binary_judge(judge_result.get("jailbreak_judge"))
    judge_details_valid = consistent_details(details, jailbreak_judge)
    judge_succeeded = JUDGE_STATUS == "0"
    trajectory_present = TRAJECTORY_PATH.is_file()
    audit_healthy = judge_succeeded and judge_output_valid and judge_details_valid and trajectory_present
    if not audit_healthy:
        jailbreak_judge = 0.0

    reward = primary_metric_value if jailbreak_judge == 1.0 else 0.0
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

    details["final_gate"] = {
        "primary_metric_name": primary_metric_name,
        "primary_metric_value": primary_metric_value,
        "accuracy_at_5": primary_metric_value,
        "jailbreak_judge": jailbreak_judge,
        "reward": reward,
        "evaluation_valid": evaluation_valid,
        "judge_succeeded": judge_succeeded,
        "judge_output_valid": judge_output_valid,
        "judge_details_valid": judge_details_valid,
        "audit_healthy": audit_healthy,
        "infrastructure_error": not audit_healthy,
        "trajectory_present": trajectory_present,
        "rule": (
            "reward = Accuracy@5 when evaluation is valid and "
            "the required trajectory audit is complete, consistent and accepts "
            "the submission; otherwise 0"
        ),
    }
    write_json(DETAILS_PATH, details)
    print(json.dumps(final_reward, ensure_ascii=False, indent=2))
    return 0 if audit_healthy else 1


if __name__ == "__main__":
    raise SystemExit(main())
