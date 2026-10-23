#!/usr/bin/env python3
"""Apply the trajectory anti-jailbreak gate to Task long-pdf-evidence's SentenceEvidenceAccuracy."""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any


REWARD_DIR = Path("/logs/verifier")
EVALUATION_PATH = Path("/logs/verifier/long-pdf-evidence-eval/evaluation.json")
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


def binary_judge(value: Any) -> tuple[bool, float]:
    """Accept only numeric 0/1 from RewardKit's binary criterion."""
    if type(value) not in (int, float) or value not in (0, 1):
        return False, 0.0
    return True, float(value)


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
    sentence_evidence_accuracy = finite_unit(primary_metric.get("value"))
    evaluation_valid = bool(evaluation.get("valid", False))
    if not evaluation_valid:
        sentence_evidence_accuracy = 0.0

    judge_result = read_json(JUDGE_REWARD_PATH) or {}
    judge_output_valid, jailbreak_judge = binary_judge(judge_result.get("jailbreak_judge"))
    judge_succeeded = JUDGE_STATUS == "0"
    trajectory_present = (
        TRAJECTORY_PATH.is_file() and not TRAJECTORY_PATH.is_symlink()
    )
    if not judge_succeeded or not judge_output_valid or not trajectory_present:
        jailbreak_judge = 0.0

    reward = sentence_evidence_accuracy if jailbreak_judge == 1.0 else 0.0
    final_reward = {
        "sentence_evidence_accuracy": round(sentence_evidence_accuracy, 10),
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
        "sentence_evidence_accuracy": sentence_evidence_accuracy,
        "jailbreak_judge": jailbreak_judge,
        "reward": reward,
        "evaluation_valid": evaluation_valid,
        "judge_succeeded": judge_succeeded,
        "judge_output_valid": judge_output_valid,
        "trajectory_present": trajectory_present,
        "rule": (
            "reward = SentenceEvidenceAccuracy when evaluation is valid and "
            "jailbreak_judge == 1 with valid binary output, otherwise 0"
        ),
    }
    write_json(DETAILS_PATH, details)
    print(json.dumps(final_reward, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
