"""Run three complete evaluations through the task's shared judge backend."""
import json
import os
from pathlib import Path


# Three fresh RewardKit evaluations share the inherited verifier sandbox.
JUDGE_REPEATS = 3


def _binary_raw(value):
    if isinstance(value, str):
        value = {"yes": 1, "no": 0}.get(value.strip().lower())
    if type(value) is bool:
        value = int(value)
    if type(value) not in (int, float) or value not in (0, 1):
        raise ValueError("Expected a binary judge criterion")
    return float(value)


def _healthy_judge_detail(value):
    import math
    if isinstance(value, list):
        return bool(value) and all(_healthy_judge_detail(item) for item in value)
    if not isinstance(value, dict) or value.get("error"):
        return False
    if value.get("kind") == "group":
        parts = value.get("components", [])
        return bool(parts) and all(_healthy_judge_detail(p.get("detail")) for p in parts)
    criteria = value.get("criteria")
    return (isinstance(criteria, list) and bool(criteria)
            and isinstance(value.get("judge_output"), str) and bool(value["judge_output"].strip())
            and all(isinstance(c, dict) and not c.get("error")
                    and _binary_raw(c.get("raw")) in (0, 1) for c in criteria))


def _mean_judge_detail(values):
    import copy
    import math
    first = values[0]
    if isinstance(first, list):
        if any(not isinstance(v, list) or len(v) != len(first) for v in values):
            raise ValueError("Judge detail layouts differ")
        return [_mean_judge_detail([v[i] for v in values]) for i in range(len(first))]
    out = copy.deepcopy(first)
    if first.get("kind") == "group":
        names = [p["name"] for p in first["components"]]
        if any([p["name"] for p in v["components"]] != names for v in values):
            raise ValueError("Judge component layouts differ")
        for i, part in enumerate(out["components"]):
            part["detail"] = _mean_judge_detail([v["components"][i]["detail"] for v in values])
    else:
        names = [c["name"] for c in first["criteria"]]
        if any([c["name"] for c in v["criteria"]] != names for v in values):
            raise ValueError("Judge criterion layouts differ")
        for i, criterion in enumerate(out["criteria"]):
            criterion["raw"] = math.fsum(_binary_raw(v["criteria"][i]["raw"]) for v in values) / JUDGE_REPEATS
            if "value" in criterion:
                criterion["value"] = math.fsum(v["criteria"][i]["value"] for v in values)/JUDGE_REPEATS
        out["judge_output"] = "\n\n".join(f"Judgment {i + 1}:\n{v['judge_output']}" for i, v in enumerate(values))
    if type(first.get("score")) in (int, float):
        out["score"] = math.fsum(v["score"] for v in values) / JUDGE_REPEATS
    return out


def run_repeated_judge(main, argv=None):
    """Average three complete, healthy judgments; retain every raw report."""
    import math
    import sys
    import tempfile
    previous_argv = sys.argv
    original = list(sys.argv if argv is None else argv)
    args = original[1:]
    if "--output" not in args or args.index("--output") + 1 == len(args):
        raise ValueError("The repeated judge requires an explicit --output")
    output_position = original.index("--output") + 1
    output = Path(original[output_position])
    output.parent.mkdir(parents=True, exist_ok=True)
    details_path = output.with_name("reward-details.json")
    output.unlink(missing_ok=True)
    details_path.unlink(missing_ok=True)
    root = Path(tempfile.mkdtemp(prefix="judge-repeats-", dir=output.parent))
    previous_logs = os.environ.get("REWARDKIT_LOG_DIR")
    measurements = []
    try:
        for repeat in range(JUDGE_REPEATS):
            folder = root / f"run-{repeat + 1}"
            folder.mkdir(mode=0o700)
            destination = folder / "reward.json"
            sys.argv = original.copy()
            sys.argv[output_position] = str(destination)
            os.environ["REWARDKIT_LOG_DIR"] = str(folder / "native")
            item = {"repeat": repeat + 1, "output": str(destination), "healthy": False}
            try:
                main()
                scores = json.loads(destination.read_text())
                details = json.loads(destination.with_name("reward-details.json").read_text())
                if (not isinstance(scores, dict) or not scores
                        or any(type(v) not in (int, float) or not math.isfinite(v) or v not in (0, 1)
                               for v in scores.values())
                        or not isinstance(details, dict) or not details
                        or not all(_healthy_judge_detail(v) for v in details.values())):
                    raise ValueError("Unhealthy judge result")
                item.update(healthy=True, scores=scores, details=details)
            except (Exception, SystemExit) as error:
                item["error_type"] = type(error).__name__
            measurements.append(item)
        if not all(item["healthy"] for item in measurements):
            raise ValueError("All three judge measurements are required")
        keys = set(measurements[0]["scores"])
        detail_keys = set(measurements[0]["details"])
        if any(set(m["scores"]) != keys or set(m["details"]) != detail_keys for m in measurements):
            raise ValueError("Judge result layouts differ")
        average = {k: math.fsum(m["scores"][k] for m in measurements) / JUDGE_REPEATS for k in keys}
        details = {k: _mean_judge_detail([m["details"][k] for m in measurements]) for k in detail_keys}
        output.write_text(json.dumps(average, indent=2, allow_nan=False) + "\n")
        details_path.write_text(json.dumps(details, indent=2, allow_nan=False) + "\n")
        status = {"healthy": True, "repeats": JUDGE_REPEATS, "aggregation": "mean", "scores": average}
        return_code = 0
    except Exception as error:
        output.write_text("{}\n")
        details_path.write_text("{}\n")
        status = {"healthy": False, "repeats": JUDGE_REPEATS, "aggregation": "mean", "error_type": type(error).__name__}
        return_code = 1
    finally:
        sys.argv = previous_argv
        if previous_logs is None:
            os.environ.pop("REWARDKIT_LOG_DIR", None)
        else:
            os.environ["REWARDKIT_LOG_DIR"] = previous_logs
    status["measurements"] = [{k: v for k, v in m.items() if k != "details"} for m in measurements]
    output.with_name("judge-repeats.json").write_text(json.dumps(status, indent=2, allow_nan=False) + "\n")
    return return_code


def main():
    import runpy
    import sys
    if len(sys.argv) < 2:
        raise ValueError("The shared judge backend path is required")
    wrapper = Path(sys.argv.pop(1)).resolve()
    if wrapper != Path(__file__).with_name("rewardkit_deepseek.py").resolve():
        raise ValueError("Use the task-provided shared judge backend")
    runpy.run_path(str(wrapper), run_name="task_rewardkit_backend")
    from rewardkit.__main__ import main as rewardkit_main
    return run_repeated_judge(rewardkit_main)


if __name__ == "__main__":
    raise SystemExit(main())
