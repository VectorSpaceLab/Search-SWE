"""Score public development predictions; timing fields are self-reported here.

The separate verifier measures its own end-to-end time and does not trust these
fields. This helper cannot access private test queries or labels.
"""

import argparse
import json
from pathlib import Path

import math
from collections import defaultdict
from statistics import mean


def query_precision(prediction, relevant, valid_ids, elapsed_sec, timeout_sec=10.0):
    """Invalid/late queries score zero; missing slots always count as misses."""
    zero = {"p10": 0.0, "p5": 0.0}
    if (isinstance(elapsed_sec, bool) or not isinstance(elapsed_sec, (int, float))
            or not math.isfinite(elapsed_sec) or elapsed_sec < 0 or elapsed_sec > timeout_sec):
        return {**zero, "status": "timeout-or-invalid-timing"}
    if not isinstance(prediction, list) or len(prediction) > 10:
        return {**zero, "status": "invalid-output"}
    if any(not isinstance(v, str) or v not in valid_ids for v in prediction):
        return {**zero, "status": "invalid-id"}
    if len(set(prediction)) != len(prediction):
        return {**zero, "status": "duplicate-id"}
    return {"p10": sum(v in relevant for v in prediction) / 10,
            "p5": sum(v in relevant for v in prediction[:5]) / 5, "status": "ok"}


def macro_precision(expected_queries, query_results, relevant_by_group, valid_ids, timeout_sec=10.0):
    """Only expected queries define the denominator; missing queries stay in it."""
    grouped = defaultdict(list)
    expected_ids = [q["id"] for q in expected_queries]
    if len(set(expected_ids)) != len(expected_ids):
        raise ValueError("Duplicate evaluation query ID")
    if set(query_results) - set(expected_ids):
        raise ValueError("Unexpected result query ID")
    for q in expected_queries:
        group = q["group_id"]
        if len(relevant_by_group[group]) < 10:
            raise ValueError("A formal group needs at least ten relevant records")
        result = query_results.get(q["id"])
        if result is None:
            score = {"p10": 0.0, "p5": 0.0, "status": "missing"}
        else:
            score = query_precision(result["ids"], relevant_by_group[group], valid_ids,
                                    result["elapsed_sec"], timeout_sec)
        grouped[group].append(score)
    if not grouped:
        raise ValueError("No evaluation groups")
    per_group = {g: {"p10": mean(s["p10"] for s in scores),
                     "p5": mean(s["p5"] for s in scores), "queries": len(scores)}
                 for g, scores in grouped.items()}
    return {"Q": mean(v["p10"] for v in per_group.values()),
            "p5": mean(v["p5"] for v in per_group.values()), "groups": per_group}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("/task/data"))
    parser.add_argument("--predictions", type=Path, required=True)
    args = parser.parse_args()
    queries = [json.loads(line) for line in (args.data_dir / "dev-queries.jsonl").read_text().splitlines()]
    groups = json.loads((args.data_dir / "dev-labels.json").read_text())
    qgroups = {qid: gid for gid, group in groups.items() for qid in group["query_ids"]}
    valid_ids = {json.loads(line)["id"] for line in (args.data_dir / "train.jsonl").read_text().splitlines()}
    results = {}
    for line in args.predictions.read_text().splitlines():
        row = json.loads(line)
        if row["query_id"] in results:
            raise ValueError("Duplicate predicted query ID")
        results[row["query_id"]] = {"ids": row["ids"], "elapsed_sec": row["elapsed_sec"]}
    score = macro_precision([{"id": q["id"], "group_id": qgroups[q["id"]]} for q in queries],
                            results, {g: set(v["record_ids"]) for g, v in groups.items()}, valid_ids)
    print(json.dumps({**score, "timing_is_self_reported": True}, indent=2))


if __name__ == "__main__":
    main()
