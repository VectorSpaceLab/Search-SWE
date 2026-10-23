"""Score public development predictions; timing fields are self-reported here.

The separate verifier measures its own end-to-end time and does not trust these
fields. This helper cannot access private test queries or labels.
"""

import argparse
import json
from pathlib import Path

from metrics import macro_precision


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
