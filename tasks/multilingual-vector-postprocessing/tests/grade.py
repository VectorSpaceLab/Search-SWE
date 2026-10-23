"""Fail-closed scoring for the fixed multilingual retrieval task."""
import json
from scoring_parameters import SCORING
from pathlib import Path
import sys

sys.path.insert(0, "/task/runtime")
from evaluate import evaluate
from metrics import reward
from isolation import cleanup

OUT = Path("/logs/verifier")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    report = {"valid": False, "reward": 0.}
    try:
        anchors = SCORING
        reward(0., anchors["baseline"], anchors["reference"])
        report = evaluate("/app/submission", "/task/data/corpus", "/private/data", "/task/data/development",
                          OUT / "evaluation", sandbox=True, require_gpu=True,
                          frozen_status="/var/tmp/submission-freeze-status.json")
        if report["total_queries"] != 13002:
            raise RuntimeError("Fixed hidden query population is incomplete")
        report.update(valid=True, baseline=anchors["baseline"], reference=anchors["reference"],
                      reward=reward(report["Q"], anchors["baseline"], anchors["reference"]))
        report["score_100"] = report["reward"] * 100
    except Exception as error:
        report = {"valid": False, "reward": 0., "failure": type(error).__name__ + ": " + str(error)}
        print(report["failure"], file=sys.stderr)
    finally:
        cleanup()
    (OUT / "report.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
