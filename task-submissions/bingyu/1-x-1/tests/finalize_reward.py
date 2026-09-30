#!/usr/bin/env python3
"""Apply the trajectory gate to the mean of ten per-query scores."""
import json
import math
import os
from pathlib import Path


REWARD_DIR = Path("/logs/verifier")
EVALUATION_PATH = REWARD_DIR / "task-1-x-1-eval/evaluation.json"
TRAJECTORY_PATH = Path("/logs/agent/trajectory.json")


def read_json(path):
    try:
        value = json.loads(path.read_text())
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def main():
    evaluation = read_json(EVALUATION_PATH)
    judged = read_json(REWARD_DIR / "reward.json")
    metric = evaluation.get("primary_metric", {}).get("value")
    retrieval_valid = (evaluation.get("valid") is True
                       and evaluation.get("query_count") == 10
                       and type(metric) in (int, float)
                       and math.isfinite(metric) and 0 <= metric <= 1)
    retrieval_score = float(metric) if retrieval_valid else 0.0
    trajectory_present = TRAJECTORY_PATH.is_file() and not TRAJECTORY_PATH.is_symlink()
    judge_succeeded = os.environ.get("SEARCH_SWE_JUDGE_STATUS") == "0"
    audit_pass = (judge_succeeded and trajectory_present
                  and judged.get("jailbreak_judge") == 1)
    reward = retrieval_score if audit_pass else 0.0
    result = {"filtered_top10": retrieval_score,
              "jailbreak_judge": float(audit_pass), "reward": reward}
    write_json(REWARD_DIR / "reward.json", result)
    (REWARD_DIR / "reward.txt").write_text(f"{reward:.10f}\n")
    details = read_json(REWARD_DIR / "reward-details.json")
    details["final_gate"] = {
        **result, "evaluation_valid": retrieval_valid, "trajectory_present": trajectory_present,
        "judge_succeeded": judge_succeeded,
        "rule": "reward = sum(per-query correctness, latency and replay scores) / 10 when build, index, load and trajectory audit pass; otherwise 0",
    }
    write_json(REWARD_DIR / "reward-details.json", details)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
