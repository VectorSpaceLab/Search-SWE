#!/usr/bin/env python3
"""Run retrieval, audit compliance, and fail closed unless both succeed."""

from __future__ import annotations

import json
import math
import os
import subprocess
import sys
from pathlib import Path


REWARD_DIR = Path("/logs/verifier")
RESULTS_DIR = REWARD_DIR / "agentic-search-vectorless-eval"
REPORT_PATH = RESULTS_DIR / "evaluation.json"
TRAJECTORY_PATH = Path("/logs/agent/trajectory.json")
PRIVATE_DIR = REWARD_DIR / ".private"
AUDIT_PATH = PRIVATE_DIR / "judge-reward.json"


def bounded(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0.0
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, number if math.isfinite(number) else 0.0))


def write_reward(report: dict, audit: dict | None = None, *, execution_ok=False,
                 audit_status=None, trajectory_present=False) -> float:
    metric = report.get("primary_metric", {}) if report.get("valid") is True else {}
    if not isinstance(metric, dict):
        metric = {}
    recall = bounded(metric.get("value")) if metric.get("name") == "GoldRecall@5" else 0.0
    audit_passed = (audit_status == 0 and trajectory_present
                    and (audit or {}).get("jailbreak_judge") in (1, True))
    reward = recall if execution_ok and audit_passed else 0.0
    verifier = REWARD_DIR
    verifier.mkdir(parents=True, exist_ok=True)
    (verifier / "reward.txt").write_text(f"{reward:.10f}\n", encoding="utf-8")
    (verifier / "reward.json").write_text(
        json.dumps(
            {
                "gold_recall_at_5": recall,
                "jailbreak_judge": float(audit_passed),
                "reward": reward,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return reward


def read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def stop_submission_processes():
    # Build/search may have left daemons; they must not run during the audit.
    for signal in ("-TERM", "-KILL"):
        subprocess.run(["/usr/bin/pkill", signal, "-u", "65534"], check=False)


def run_audit() -> int:
    PRIVATE_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    PRIVATE_DIR.chmod(0o700)
    AUDIT_PATH.unlink(missing_ok=True)
    judge_task = PRIVATE_DIR / "judge-task"
    with (RESULTS_DIR / "audit.stdout.log").open("w") as stdout, \
            (RESULTS_DIR / "audit.stderr.log").open("w") as stderr:
        configure = subprocess.run([
            sys.executable, "/tests/configure_trajectory_judge.py",
            "--template", "/tests/jailbreak_judge/codex.toml",
            "--output", str(judge_task),
        ], stdout=stdout, stderr=stderr, timeout=30, check=False)
        if configure.returncode:
            return configure.returncode
        # Judge credentials stay verifier-only; submission keys are not needed.
        env = {key: value for key, value in os.environ.items()
               if key in {"PATH", "HOME", "LANG", "OPENAI_BASE_URL", "OPENAI_API_KEY",
                          "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "http_proxy",
                          "https_proxy", "no_proxy", "LITELLM_LOCAL_MODEL_COST_MAP"}}
        result = subprocess.run([
            "/usr/bin/timeout", "--signal=TERM", "--kill-after=30s", "3600s",
            sys.executable, str(Path(__file__).with_name("rewardkit_deepseek.py")), str(judge_task),
            "--workspace", "/app", "--output", str(AUDIT_PATH),
            "--max-concurrent-agent", "1", "--judge", "deepseek-codex",
            "--model", "deepseek/deepseek-v4.1-flash",
        ], stdout=stdout, stderr=stderr, env=env, timeout=3660, check=False)
    return result.returncode


def main() -> int:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.unlink(missing_ok=True)
    # Never expose a positive retrieval-only reward before the mandatory audit.
    write_reward({})
    command = [
        sys.executable,
        "/tests/run_submission.py",
        "--submission-dir", "/app",
        "--corpus", "/task/data/corpus.jsonl",
        "--queries", "/tests/data/queries.jsonl",
        "--qrels", "/tests/data/qrels_gold.txt",
        "--results-dir", str(RESULTS_DIR),
        "--evaluator", "/tests/evaluate.py",
        "--build-timeout", "600",
        "--score-timeout", "120",
        "--query-concurrency", "5",
    ]
    try:
        # One shared execution budget; queries have no individual timeout.
        completed = subprocess.run(command, check=False, timeout=15300)
    except Exception as error:
        REPORT_PATH.write_text(
            json.dumps({"valid": False, "score": 0.0, "errors": [str(error)]}) + "\n",
            encoding="utf-8",
        )
        completed = None
    finally:
        stop_submission_processes()
    report = read_json(REPORT_PATH)
    execution_ok = completed is not None and completed.returncode == 0 and report.get("valid") is True
    trajectory_present = (TRAJECTORY_PATH.is_file() and not TRAJECTORY_PATH.is_symlink()
                          and bool(read_json(TRAJECTORY_PATH)))
    audit_status = None
    if trajectory_present:
        try:
            audit_status = run_audit()
        except (OSError, subprocess.TimeoutExpired) as error:
            (RESULTS_DIR / "audit-error.txt").write_text(type(error).__name__ + "\n")
    audit = read_json(AUDIT_PATH) if audit_status == 0 else {}
    reward = write_reward(report, audit, execution_ok=execution_ok,
                          audit_status=audit_status, trajectory_present=trajectory_present)
    print(json.dumps({"submission_returncode": completed.returncode if completed else None,
                      "audit_returncode": audit_status, "reward": reward}))
    # A clear audit rejection is a valid zero. Missing/broken audit is an error.
    audit_valid = type(audit.get("jailbreak_judge")) in (int, float, bool) and audit.get("jailbreak_judge") in (0, 1)
    return 0 if execution_ok and trajectory_present and audit_status == 0 and audit_valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
