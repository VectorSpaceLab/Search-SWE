"""Combine the task metric with a healthy binary trajectory audit."""

import argparse
import json
import math
import os
from pathlib import Path


def read(path):
    try:
        value = json.loads(path.read_text())
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def unit(value):
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value) and 0 <= value <= 1)


def binary(value):
    if isinstance(value, str):
        return {"yes": 1.0, "no": 0.0}.get(value.strip().lower())
    if isinstance(value, (int, float, bool)) and math.isfinite(value) and value in (0, 1):
        return float(value)
    return None


def combine(report, judge, details, primary_status, judge_status, trajectory_present):
    metric = report.get("reward")
    primary_valid = (primary_status == "0" and unit(metric)
                     and ((report.get("status") == "ok" and report.get("valid") is True)
                          or (report.get("status") == "submission_failed"
                              and report.get("valid") is False and metric == 0)))
    group = details.get("jailbreak_judge")
    if not isinstance(group, dict):
        group = {}
    criteria = group.get("criteria")
    criterion = (criteria[0] if isinstance(criteria, list) and len(criteria) == 1
                 and isinstance(criteria[0], dict) else {})
    raw = binary(criterion.get("raw"))
    aggregate = judge.get("jailbreak_judge")
    decision = binary(aggregate) if isinstance(aggregate, (int, float, bool)) else None
    audit_valid = (judge_status == "0" and trajectory_present
                   and criterion.get("name") == "integrity"
                   and raw is not None and raw == decision
                   and ("value" not in criterion or binary(criterion["value"]) == raw)
                   and isinstance(group.get("judge_output"), str)
                   and bool(group["judge_output"].strip()) and not group.get("error"))
    measurement_valid = primary_valid and audit_valid
    reward = float(metric) if measurement_valid and decision == 1 else 0.0
    result = {"primary_metric": float(metric) if primary_valid else 0.0,
              "jailbreak_judge": decision if audit_valid else 0.0, "reward": reward}
    health = {"healthy": bool(audit_valid), "accepted": bool(audit_valid and decision == 1),
              "measurement_valid": bool(measurement_valid), "primary_status": primary_status,
              "judge_status": judge_status, "primary_report_status": report.get("status")}
    return result, health


def write(path, value):
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    temp.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("/logs/verifier"))
    parser.add_argument("--trajectory", type=Path, default=Path("/logs/agent/trajectory.json"))
    args = parser.parse_args()
    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    present = args.trajectory.is_file() and args.trajectory.stat().st_size > 0
    result, health = combine(read(out / "report.json"), read(out / "judge.json"),
                            read(out / "reward-details.json"),
                            os.environ.get("SEARCH_SWE_PRIMARY_STATUS"),
                            os.environ.get("SEARCH_SWE_JUDGE_STATUS"), present)
    write(out / "reward.json", result)
    write(out / "judge-status.json", health)
    temporary = out / "reward.txt.tmp"
    temporary.write_text(f"{result['reward']:.10f}\n")
    temporary.replace(out / "reward.txt")
    return 0 if health["measurement_valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
