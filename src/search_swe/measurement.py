"""Interpret verifier diagnostics for both batch runs and regrades."""

import json


def _report(path):
    try:
        value = json.loads(path.read_text())
    except (OSError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def cgroup_measurement_valid(path):
    """Return None for no diagnostic and False for invalid or unreadable evidence."""
    try:
        status = json.loads(path.read_text())
    except FileNotFoundError:
        return None
    except (OSError, ValueError):
        return False
    return isinstance(status, dict) and status.get("measurement_valid") is True


def _multilingual_submission_zero(verifier, status, reward):
    # This finalizer marks every nonzero primary exit invalid, including the
    # collector rejecting a submission that violates the task's file contract.
    if (reward != 0 or status.get("healthy") is not True or status.get("exit_status") != "0"
            or status.get("primary_exit_status") != "1"):
        return False
    report = _report(verifier / "report.json")
    if report.get("valid") is not False or report.get("reward") != 0:
        return False
    # Match the verifier's complete cause chain. A failed copy, missing host
    # metadata or an unrecognized error still represents a failed measurement.
    prefix = ("ContractViolation: Invalid frozen submission: Collected artifact restoration failed: "
              "Invalid frozen submission: ")
    failure = report.get("failure")
    return isinstance(failure, str) and failure.startswith(prefix) and failure[len(prefix):] in {
        "Submission root must be a real directory", "Linked or non-directory submission entry",
        "Linked or non-regular submission entry", "Missing transform.py",
        "Submission exceeds the total storage limit", "100 GiB total task storage exceeded",
    }


def verifier_measurement(verifier, task_name, reward):
    """Return (valid, failure kind). None means the verifier gave no health signal."""
    valid = cgroup_measurement_valid(verifier / "cgroup-status.json")
    if valid is False:
        return False, "cgroup_environment"
    task = task_name.rsplit("/", 1)[-1]
    evaluation = _report(verifier / f"{task}-eval/evaluation.json")
    errors = evaluation.get("judge_error_count")
    if evaluation.get("valid") is False and type(errors) is int and errors > 0:
        return False, "answer_judging"

    for filename in ("reward-details.json", "judge-status.json"):
        data = _report(verifier / filename)
        guard = data.get("timeout_guard")
        phase = guard.get("failed_phase") if isinstance(guard, dict) else None
        if isinstance(phase, str) and phase.strip():
            return False, "verifier_timeout"
        for details in (data, data.get("final_gate")):
            if not isinstance(details, dict):
                continue
            flag = details.get("measurement_valid")
            if flag is False:
                if not (task == "multilingual-vector-postprocessing" and filename == "judge-status.json"
                        and details is data and _multilingual_submission_zero(verifier, data, reward)):
                    return False, "verifier_measurement"
                valid = True
            elif flag is True:
                valid = True
            elif details.get("evaluation_valid") is True and details.get("judge_succeeded") is False:
                return False, "judge_infrastructure"
    return valid, None
