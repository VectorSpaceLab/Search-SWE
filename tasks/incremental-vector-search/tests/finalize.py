"""A failed/missing semantic audit cannot become a successful benchmark run."""
import json
import math
import os
from pathlib import Path


def finalize(evaluation, audit, status, trajectory_present):
    value = evaluation.get("raw_reward")
    valid = (evaluation.get("valid") is True and type(value) in (int, float)
             and math.isfinite(value) and 0 <= value <= 1)
    audit_value = audit.get("integrity_judge")
    healthy = (status == "0" and trajectory_present and
               type(audit_value) in (int, float) and audit_value in (0, 1))
    passed = healthy and audit_value == 1
    return {"reward": value if valid and passed else 0.0,
            "raw_reward": value if valid else 0.0, "integrity": float(passed)}, bool(valid and healthy)


if __name__ == "__main__":
    root = Path("/logs/verifier")
    try:
        reward, healthy = finalize(json.loads((root / "evaluation.json").read_text()),
            json.loads((root / "audit.json").read_text()), os.environ.get("SEARCH_SWE_JUDGE_STATUS"),
            Path("/logs/agent/trajectory.json").is_file())
    except (OSError, ValueError, TypeError):
        reward, healthy = {"reward": 0.0, "raw_reward": 0.0, "integrity": 0.0}, False
    (root / "audit-status.json").write_text(json.dumps({**reward, "healthy": healthy}, allow_nan=False) + "\n")
    (root / "reward.json").write_text(json.dumps({"reward": reward["reward"]}, allow_nan=False) + "\n")
    (root / "reward.txt").write_text(f"{reward['reward']:.12f}\n")
    raise SystemExit(0 if healthy else 1)
