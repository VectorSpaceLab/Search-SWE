"""Paired efficiency evaluation using the immutable execution supervisor."""

import argparse
import json
import math
from pathlib import Path
from types import SimpleNamespace

import grade
from efficiency_metrics import efficiency_score, latency_metric, quality_gate


def run_phase(args, config, name, submission, *, control=False):
    options = vars(args).copy()
    options.update(submission=submission, work=args.work/name, logs=args.logs/name)
    phase = dict(config, raw_efficiency_phase=True, measure_gpu_memory=True)
    if control:
        phase.update(prepare_timeout_sec=300, query_timeout_sec=5)
    status = grade.main(SimpleNamespace(**options), phase)
    report = json.loads((options["logs"] / "evaluation.json").read_text())
    if status or report["infrastructure_error"]:
        raise RuntimeError(f"{name} infrastructure failure: {report.get('infrastructure_message')}")
    return report


def measured(report):
    rounds = [[row for row in report["queries"] if row["repetition"] == repetition]
              for repetition in range(len(report["passes"]))]
    return latency_metric(rounds), report["gpu_memory"]["peak_above_idle_bytes"]


def main():
    parser = argparse.ArgumentParser()
    for name, default in [("submission", "/app/submission"), ("data", "/task/data"),
                          ("models", "/task/models"), ("private", "/tests/data"),
                          ("work", "/work/tracing"), ("logs", "/logs/verifier")]:
        parser.add_argument("--"+name, type=Path, default=Path(default))
    args = parser.parse_args()
    args.logs.mkdir(parents=True, exist_ok=True, mode=0o700)
    args.logs.chmod(0o700)
    (args.logs / "reward.txt").write_text("0\n")
    result = dict(valid_task_inputs=False, submission_valid=False, reward=0., infrastructure_error=False)
    try:
        config = json.loads((args.private / "evaluation-config.json").read_text())
        reference = config["reference_cost_ratio"]
        if (config["score_kind"] != "quality-gated-efficiency-v1" or config["repetitions"] != 3
                or (reference is None and not config.get("author_calibration"))
                or (reference is not None and (isinstance(reference, bool)
                    or not isinstance(reference, (int, float)) or not math.isfinite(reference)
                    or not 0 < reference <= .5))):
            raise ValueError("Invalid or uncalibrated efficiency configuration")
        args.work.mkdir(parents=True, mode=0o755)
        args.work.chmod(0o755)
        candidate = run_phase(args, config, "candidate", args.submission)
        result.update(valid_task_inputs=candidate["valid_task_inputs"],
                      submission_valid=candidate["submission_valid"])
        if not candidate["submission_valid"]:
            result["submission_error"] = candidate.get("submission_error", "Invalid candidate")
        else:
            control = run_phase(args, config, "control", Path("/control"), control=True)
            if not control["submission_valid"]:
                raise RuntimeError("Immutable control failed preparation/execution")
            control_time, control_memory = measured(control)
            latency, memory = measured(candidate)
            if not quality_gate(control["passes"]):
                raise RuntimeError("Immutable control failed the fixed quality floor")
            result.update(candidate_quality=candidate["passes"], control_quality=control["passes"],
                          latency_sec=latency, gpu_memory_bytes=memory,
                          control_latency_sec=control_time, control_gpu_memory_bytes=control_memory,
                          reference_cost_ratio=reference,
                          paired_cost_ratio=(latency/control_time)*(max(1024**3, memory)
                                                                  /max(1024**3, control_memory)))
            if reference is None:
                result.update(author_calibration=True, normalized_score_defined=False)
            else:
                score = efficiency_score(candidate["passes"], latency, memory,
                                         control_time, control_memory, reference)
                result.update(**score, normalized_score_defined=True, reward=score["score"]/100)
    except Exception as error:
        result.update(infrastructure_error=True, reward=0., infrastructure_exception=type(error).__name__,
                      infrastructure_message=str(error))
    finally:
        grade.kill_new_processes({})
        grade.write_json(args.logs / "evaluation.json", result)
    print(json.dumps(result))
    return int(result["infrastructure_error"])


if __name__ == "__main__":
    raise SystemExit(main())
