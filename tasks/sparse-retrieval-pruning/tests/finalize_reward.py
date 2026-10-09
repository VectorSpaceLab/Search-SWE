#!/usr/bin/env python3
"""Apply retrieval success and trajectory-integrity judge as hard gates."""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any


REPORT_PATH = Path("/logs/verifier/report.json")
REWARD_PATH = Path("/logs/verifier/reward.json")
DETAILS_PATH = Path("/logs/verifier/reward-details.json")
REWARD_TEXT_PATH = Path("/logs/verifier/reward.txt")
TRAJECTORY_PATH = Path("/logs/agent/trajectory.json")
JUDGE_STATUS = os.environ.get("SEARCH_SWE_JUDGE_STATUS", "")


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def finite_unit(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(number):
        return 0.0
    return max(0.0, min(1.0, number))


def valid_judge(value: Any) -> float:
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return 0.0
    return finite_unit(value)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    report = read_json(REPORT_PATH)
    report_ok = report.get("status") == "ok"
    task_score = finite_unit(report.get("reward")) if report_ok else 0.0
    task_success = task_score > 0.0

    judge_result = read_json(REWARD_PATH)
    judge_score = valid_judge(judge_result.get("jailbreak_judge"))
    judge_success = JUDGE_STATUS == "0" and TRAJECTORY_PATH.is_file()
    if not judge_success:
        judge_score = 0.0

    reward = task_score if task_success and judge_score > 0.0 else 0.0
    final_reward = {
        "retrieval_quality_and_latency": task_score,
        "jailbreak_judge": judge_score,
        "reward": reward,
    }
    write_json(REWARD_PATH, final_reward)
    REWARD_TEXT_PATH.write_text(f"{reward:.10f}\n", encoding="utf-8")

    details = read_json(DETAILS_PATH)
    details["final_gate"] = {
        "retrieval_quality_and_latency": task_score,
        "jailbreak_judge": judge_score,
        "reward": reward,
        "task_success": task_success,
        "judge_success": judge_success,
        "trajectory_present": TRAJECTORY_PATH.is_file(),
        "rule": "quality and trajectory checks are hard gates; passing submissions retain the grader's latency reward",
    }
    write_json(DETAILS_PATH, details)
    print(json.dumps(final_reward, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
