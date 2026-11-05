"""Trusted frozen-vector retrieval and phase/latency accounting."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile
import threading
import time

import numpy as np
from threadpoolctl import threadpool_limits
from metrics import aggregate, normalize, quality
from process import TransformError, TransformProcess
from storage import StorageBudget


MEASUREMENT_ROUNDS = 5
AUDIT_SEED = 0


class ContractViolation(RuntimeError):
    pass


def rows(path):
    result = [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]
    if not result:
        raise ContractViolation("Empty metadata file")
    return result


def inputs(directory, kind):
    metadata = rows(Path(directory) / ("documents.jsonl" if kind == "documents" else "queries.jsonl"))
    ids = [r["id"] for r in metadata]
    if not all(isinstance(i, str) and i for i in ids) or len(set(ids)) != len(ids):
        raise ContractViolation("Invalid or duplicate input IDs")
    vectors = np.load(Path(directory) / "vectors.npy", allow_pickle=False).astype(np.float32)
    if vectors.shape != (len(metadata), 1024) or not np.isfinite(vectors).all():
        raise ContractViolation("Invalid fixed vectors")
    order = sorted(range(len(ids)), key=lambda i: ids[i])
    return [metadata[i] for i in order], vectors[order]


def verify_snapshot(submission, status_path, *, make_read_only=True):
    status = json.loads(Path(status_path).read_text())
    if status.get("valid") is not True:
        raise ContractViolation("Invalid frozen submission: " + str(status.get("reason")))
    submission = Path(submission)
    if submission.is_symlink() or not submission.is_dir():
        raise ContractViolation("Linked submission root")
    expected = {r["path"]: r for r in status["files"]}
    actual = {}
    for parent, directories, files in os.walk(submission, followlinks=False):
        for name in directories:
            if (Path(parent) / name).is_symlink():
                raise ContractViolation("Linked submission directory")
        for name in files:
            path = Path(parent) / name
            if path.is_symlink() or not path.is_file():
                raise ContractViolation("Non-regular submission entry")
            relative = str(path.relative_to(submission))
            if relative not in expected:
                raise ContractViolation("Submission changed after collection")
            record = expected[relative]
            if path.stat().st_size != record["size_bytes"]:
                raise ContractViolation("Frozen submission size mismatch")
            with path.open("rb") as handle:
                if hashlib.file_digest(handle, "sha256").hexdigest() != record["sha256"]:
                    raise ContractViolation("Frozen submission hash mismatch")
            # The copied artifact may have framework-selected ownership/modes;
            # establish read-only candidate access in this independent verifier.
            if make_read_only:
                mode = path.stat().st_mode
                os.chown(path, 0, 0)
                path.chmod(0o555 if mode & 0o111 else 0o444)
            actual[relative] = True
    if set(actual) != set(expected) or "transform.py" not in actual:
        raise ContractViolation("Frozen submission is incomplete")
    if make_read_only:
        for parent, directories, files in os.walk(submission, topdown=False):
            os.chown(parent, 0, 0)
            Path(parent).chmod(0o555)


class Meter:
    def __init__(self, require_gpu):
        self.stopped = threading.Event()
        self.gpu_peak = 0
        self.memory_peak = 0
        self.nvml = None
        self.handle = None
        self.storage = StorageBudget()
        self.storage.check(force=True)
        self.storage_error = None
        if require_gpu:
            import subprocess
            devices = subprocess.check_output(["nvidia-smi", "--query-gpu=uuid", "--format=csv,noheader,nounits"], text=True).strip().splitlines()
            if len(devices) != 1:
                raise RuntimeError("Verifier infrastructure must expose exactly one reserved GPU")
            uuid = devices[0].strip()
            import pynvml
            pynvml.nvmlInit()
            self.nvml = pynvml
            self.handle = pynvml.nvmlDeviceGetHandleByUUID(uuid)
            self.gpu_uuid = uuid
        self.thread = threading.Thread(target=self.sample, daemon=True)
        self.thread.start()

    def sample(self):
        while not self.stopped.wait(.05):
            try:
                self.storage.check()
            except Exception as error:
                self.storage_error = error
            try:
                if self.nvml:
                    self.gpu_peak = max(self.gpu_peak, self.nvml.nvmlDeviceGetMemoryInfo(self.handle).used)
                path = Path("/sys/fs/cgroup/memory.current")
                if path.exists():
                    self.memory_peak = max(self.memory_peak, int(path.read_text()))
            except (OSError, ValueError):
                pass

    def check(self):
        if self.storage_error is not None:
            raise ContractViolation(str(self.storage_error)) from self.storage_error

    def close(self):
        self.stopped.set()
        self.thread.join(timeout=2)
        if self.nvml:
            self.nvml.nvmlShutdown()


def equivalent(a, b):
    # Permit floating-point kernel differences across batch shapes while
    # rejecting meaningful changes in the effective transformation.
    return np.max(np.linalg.norm(normalize(a) - normalize(b), axis=1)) <= .01


def evaluate_once(submission, corpus, query_root, development, output, *, sandbox=False,
                  require_gpu=True, preparation_seconds=1800, query_seconds=.5):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    start = time.monotonic()
    prepare_deadline = start + preparation_seconds
    worker = None
    meter = Meter(require_gpu)
    temporary = tempfile.TemporaryDirectory(prefix="transform-work-", dir="/tmp")
    records = []
    caches = {}
    audit_rng = np.random.default_rng(AUDIT_SEED)
    memory_events = Path("/sys/fs/cgroup/memory.events")
    before_events = memory_events.read_text() if memory_events.exists() else ""
    try:
        worker = TransformProcess(submission, temporary.name, output / "worker.stderr.log",
                                  prepare_deadline, sandbox=sandbox, require_gpu=require_gpu)
        for dataset in ("belebele", "xquad"):
            metadata, raw = inputs(Path(corpus) / dataset, "documents")
            converted = []
            for begin in range(0, len(raw), 128):
                meter.check()
                converted.append(normalize(worker.transform(raw[begin:begin + 128],
                    [r["language"] for r in metadata[begin:begin + 128]], prepare_deadline)))
            converted = np.concatenate(converted)
            caches[dataset] = dict(metadata=metadata, raw=raw, vectors=converted,
                                   ids=np.array([r["id"] for r in metadata]))
            # Repeated document inputs after reordering must preserve f.
            selected = audit_rng.choice(len(raw), size=min(12, len(raw)), replace=False)
            changed = worker.transform(raw[selected], [metadata[i]["language"] for i in selected], prepare_deadline)
            if not equivalent(changed, converted[selected]):
                raise ContractViolation("Transform depends on document order or batch shape")
        # Warm only with public development queries. Hidden queries are not sent
        # to the candidate during loading or preparation.
        public_metadata, public_vectors = inputs(Path(development) / "belebele", "queries")
        for i in range(min(4, len(public_vectors))):
            worker.transform(public_vectors[i:i + 1], [public_metadata[i]["language"]], prepare_deadline)
        if time.monotonic() > prepare_deadline:
            raise ContractViolation("Document preparation exceeded its limit")
        prepared = time.monotonic() - start
        meter.check()
        queued = []
        for dataset in ("belebele", "xquad"):
            metadata, vectors = inputs(Path(query_root) / dataset, "queries")
            labels = rows(Path(query_root) / dataset / "qrels.jsonl")
            qrels = {r["query_id"]: r["relevant_doc_ids"] for r in labels}
            if len(qrels) != len(labels) or set(qrels) != {r["id"] for r in metadata}:
                raise ContractViolation("Query/qrels coverage mismatch")
            corpus_ids = set(caches[dataset]["ids"])
            for i, row in enumerate(metadata):
                relevant = qrels[row["id"]]
                if len(relevant) != len(set(relevant)) or len(relevant) != (10 if dataset == "belebele" else 6) or not set(relevant) <= corpus_ids:
                    raise ContractViolation("Invalid fixed relevance set")
                queued.append((dataset, row, vectors[i:i + 1], relevant))
        audit_rng.shuffle(queued)
        longest = 0.
        failed = 0
        probe_failures = []
        for index, (dataset, row, vector, relevant) in enumerate(queued):
            meter.check()
            began = time.monotonic()
            valid, reason, ranked_ids = False, None, []
            if worker is not None:
                try:
                    transformed = normalize(worker.transform(vector, [row["language"]], began + query_seconds))[0]
                    cache = caches[dataset]
                    with threadpool_limits(limits=1, user_api="blas"):
                        scores = cache["vectors"] @ transformed
                    order = np.argsort(-scores, kind="stable")[:20]
                    ranked_ids = cache["ids"][order].tolist()
                    # Materialize the complete Top-20 response inside the same
                    # deadline as conversion, cosine search and ranking.
                    json.dumps({"document_ids": ranked_ids}, separators=(",", ":")).encode("utf-8")
                    elapsed = time.monotonic() - began
                    if elapsed > query_seconds:
                        raise TimeoutError("Full query exceeded its limit")
                    valid = True
                except TransformError as error:
                    if str(error) in {"OutOfMemoryError", "MemoryError"}:
                        raise ContractViolation("Submission exhausted its memory budget") from error
                    reason = "transform-error:" + str(error)
                except (ValueError, TimeoutError, RuntimeError, OSError) as error:
                    reason = type(error).__name__
                    if isinstance(error, (TimeoutError, RuntimeError, OSError)):
                        worker.close()
                        worker = None
            else:
                reason = "transform-unavailable-after-failure"
            elapsed = time.monotonic() - began
            longest = max(longest, elapsed)
            ndcg, recall = quality(ranked_ids, relevant) if valid else (0., 0.)
            failed += not valid
            records.append(dict(query_id=row["id"], dataset=dataset, language=row["language"],
                                ndcg=ndcg, recall=recall, valid=valid, seconds=elapsed, failure=reason,
                                ranked_doc_ids=ranked_ids if valid else []))
            if worker is not None and index % 127 == 0:
                cache = caches[dataset]
                i = int(audit_rng.integers(len(cache["raw"])))
                try:
                    check = worker.transform(cache["raw"][i:i + 1], [cache["metadata"][i]["language"]], time.monotonic() + query_seconds)
                except (TimeoutError, RuntimeError, OSError) as error:
                    # A transport/timing failure ends only this measurement round.
                    # A successfully returned but changed vector remains a violation.
                    probe_failures.append({"after_query": row["id"], "failure": type(error).__name__})
                    worker.close()
                    worker = None
                else:
                    if not equivalent(check, cache["vectors"][i:i + 1]):
                        raise ContractViolation("The frozen function changed during query evaluation")
        meter.check()
        meter.storage.check(force=True)
        if memory_events.exists():
            def oom(text):
                return int(dict(line.split() for line in text.splitlines()).get("oom_kill", "0"))
            if oom(memory_events.read_text()) > oom(before_events):
                raise ContractViolation("Container memory limit was exceeded")
        report = {**aggregate(records), "valid_queries": len(records) - failed, "total_queries": len(records),
                  "consistency_probe_failures": probe_failures,
                  "preparation_seconds": prepared, "max_query_seconds": longest,
                  "evaluation_seconds": time.monotonic() - start, "gpu_peak_bytes": meter.gpu_peak,
                  "task_storage_peak_bytes": meter.storage.peak_bytes,
                  "fixed_input_bytes": meter.storage.fixed_bytes,
                  "container_memory_sample_peak_bytes": meter.memory_peak,
                  "gpu_uuid": getattr(meter, "gpu_uuid", None),
                  "cgroup_limits": {name: (Path("/sys/fs/cgroup") / name).read_text().strip()
                                    for name in ("cpu.max", "memory.max", "memory.swap.max", "pids.max")
                                    if (Path("/sys/fs/cgroup") / name).exists()},
                  "consistency_normalized_l2_tolerance": .01, "queries": records}
        (output / "evaluation.json").write_text(json.dumps(report, indent=2))
        return report
    finally:
        if worker is not None:
            worker.close()
        meter.close()
        temporary.cleanup()


def median_queries(rounds, query_seconds):
    """Select each query's median timing sample, without consulting its quality."""
    if len(rounds) != MEASUREMENT_ROUNDS:
        raise ContractViolation("Five complete measurement rounds are required")
    keys = [(r["dataset"], r["language"], r["query_id"]) for r in rounds[0]["queries"]]
    for report in rounds:
        if [(r["dataset"], r["language"], r["query_id"]) for r in report["queries"]] != keys:
            raise ContractViolation("Measurement query populations or order differ")
    records = []
    for samples in zip(*(report["queries"] for report in rounds)):
        # Failures occupy the deadline, not their often near-zero failure time.
        durations = [min(query_seconds, max(0., r["seconds"])) if r["valid"]
                     else query_seconds for r in samples]
        selected = sorted(range(MEASUREMENT_ROUNDS),
                          key=lambda i: (durations[i], not samples[i]["valid"], i))[2]
        record = dict(samples[selected], seconds=durations[selected], selected_round=selected + 1,
                      measurement_seconds=durations,
                      measurement_valid=[r["valid"] for r in samples])
        records.append(record)
    return records


def evaluate(submission, corpus, query_root, development, output, *, sandbox=False,
             require_gpu=True, preparation_seconds=1800, query_seconds=.5, frozen_status=None):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    if frozen_status:
        verify_snapshot(submission, frozen_status)
    rounds = []
    for number in range(1, MEASUREMENT_ROUNDS + 1):
        # Each round creates and closes its own worker, caches and temporary directory.
        rounds.append(evaluate_once(submission, corpus, query_root, development,
                                    output / f"round-{number}", sandbox=sandbox,
                                    require_gpu=require_gpu, preparation_seconds=preparation_seconds,
                                    query_seconds=query_seconds))
    records = median_queries(rounds, query_seconds)
    report = {**aggregate(records), "queries": records, "total_queries": len(records),
              "valid_queries": sum(r["valid"] for r in records),
              "measurement_rounds": MEASUREMENT_ROUNDS,
              "measurement_aggregation": "per-query median duration; quality from the same sample",
              "measurement_reports": [{k: v for k, v in r.items() if k != "queries"} for r in rounds],
              "preparation_seconds": max(r["preparation_seconds"] for r in rounds),
              "max_query_seconds": max(r["seconds"] for r in records),
              "evaluation_seconds": sum(r["evaluation_seconds"] for r in rounds),
              "gpu_uuid": rounds[0]["gpu_uuid"], "cgroup_limits": rounds[0]["cgroup_limits"],
              "consistency_normalized_l2_tolerance": .01,
              **{key: max(r[key] for r in rounds) for key in
                 ("gpu_peak_bytes", "container_memory_sample_peak_bytes", "task_storage_peak_bytes", "fixed_input_bytes")}}
    (output / "evaluation.json").write_text(json.dumps(report, indent=2, allow_nan=False))
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--submission", default="/app/submission")
    parser.add_argument("--output", default="/app/development-evaluation")
    args = parser.parse_args()
    report = evaluate(args.submission, "/task/data/corpus", "/task/data/development", "/task/data/development", args.output)
    print(json.dumps({k: v for k, v in report.items() if k != "queries"}, indent=2))


if __name__ == "__main__":
    main()
