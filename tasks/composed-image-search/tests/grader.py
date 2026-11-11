#!/usr/bin/env python3
import json, os, shutil, subprocess, time
from pathlib import Path
from evaluation import read_jsonl, validate, quality, aggregate
from batch_runtime import completed_rows, independent_budget

UID = GID = 10001
LOG = Path("/logs/verifier/composed-image-search-eval")
WORK = Path("/work")


def dump(p, x):
    p.write_text(json.dumps(x, indent=2, allow_nan=False) + "\n")


def stop():
    for sig in ["TERM", "KILL"]:
        subprocess.run(
            ["/usr/bin/pkill", "-" + sig, "-u", "submission"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if sig == "TERM":
            time.sleep(0.2)


def child_env():
    e = {
        "HOME": "/work/index",
        "USER": "submission",
        "LOGNAME": "submission",
        "JAVA_HOME": "/opt/java/openjdk",
        "PATH": "/opt/conda/bin:/opt/java/openjdk/bin:/usr/local/bin:/usr/bin:/bin",
        "LANG": "C.UTF-8",
        "PYTHONUNBUFFERED": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "LD_LIBRARY_PATH": os.environ.get("LD_LIBRARY_PATH", "/usr/local/nvidia/lib:/usr/local/nvidia/lib64"),
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
        "TMPDIR": "/work/index/tmp",
        "XDG_CACHE_HOME": "/work/index/cache",
    }
    for k in [
        "OPENROUTER_API_KEY",
        "JINA_API_KEY",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "NO_PROXY",
        "http_proxy",
        "https_proxy",
        "no_proxy",
    ]:
        if os.environ.get(k):
            e[k] = os.environ[k]
    return e


def command(args):
    return [
        "/usr/sbin/runuser",
        "--preserve-environment",
        "-u",
        "submission",
        "--",
        "/usr/bin/setpriv",
        "--no-new-privs",
        *args,
    ]


def run(args, label, timeout):
    t = time.monotonic()
    with (
        (LOG / (label + ".stdout.log")).open("wb") as out,
        (LOG / (label + ".stderr.log")).open("wb") as err,
    ):
        p = subprocess.Popen(
            command(args),
            cwd="/app",
            env=child_env(),
            stdout=out,
            stderr=err,
            start_new_session=True,
        )
        try:
            code = p.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            stop()
            p.wait(timeout=10)
            raise ValueError(label + " timed out")
    if code:
        raise ValueError(label + " exited " + str(code))
    return time.monotonic() - t


def main():
    LOG.mkdir(parents=True, exist_ok=True)
    report = {
        "valid": False,
        "errors": [],
        "primary_metric": {"name": "ComposedSourceQuality", "value": 0.0},
    }
    try:
        if os.environ.get("SEARCH_SWE_EXECUTION_ERROR"):
            raise ValueError(os.environ["SEARCH_SWE_EXECUTION_ERROR"])
        queries = read_jsonl("/tests/data/queries.jsonl")
        gold = {
            x["query_id"]: x["qrels"] for x in read_jsonl("/tests/data/labels.jsonl")
        }
        pages = {
            x["image_id"]: x for x in read_jsonl("/task/data/corpus/records.jsonl")
        }
        assert len(pages) == 125226
        assert all(
            q["reference_image_id"] in pages
            and isinstance(q["modification"], str)
            and isinstance(q["shared_concept"], str)
            for q in queries
        )
        assert len({q["query_id"] for q in queries}) == len(queries) and set(gold) == {
            q["query_id"] for q in queries
        }
        groups = {
            x["query_id"]: x["group"] for x in read_jsonl("/tests/data/labels.jsonl")
        }
        report["inputs_verified"] = True
        if WORK.exists():
            shutil.rmtree(WORK)
        WORK.mkdir(mode=0o711)
        WORK.chmod(0o711)
        for name in ["input", "index", "output"]:
            p = WORK / name
            p.mkdir()
            os.chown(p, 0 if name == "input" else UID, GID)
            p.chmod(0o750)
        for name in ["tmp", "cache"]:
            p = WORK / "index" / name
            p.mkdir(mode=0o700)
            os.chown(p, UID, GID)
        checks = " && ".join(
            [
                "test -x /app/build.sh",
                "test -x /app/run.sh",
                "test -r /task/data/corpus/records.jsonl",
                "test ! -r /tests/data/labels.jsonl",
                "test ! -r /tests/grader.py",
                "test ! -r /logs/agent/trajectory.json",
                "test ! -w /logs/verifier",
                "test ! -w /app",
                'test -z "$' + '{OPENAI_API_KEY+x}"',
                "test ! -r /proc/1/environ",
            ]
        )
        subprocess.run(
            command(["/bin/sh", "-c", checks]),
            check=True,
            env=child_env(),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        report["permission_boundary_checked"] = True
        report["build_seconds"] = run(
            [
                "/app/build.sh",
                "--corpus",
                "/task/data/corpus",
                "--index-dir",
                "/work/index",
            ],
            "build",
            3600,
        )
        rows = []
        predictions = []
        elapsed = 0.0
        midpoint = (len(queries) + 1) // 2
        batches = [queries[:midpoint], queries[midpoint:]]
        for i, qs in enumerate(batches, 1):
            qp = WORK / "input" / f"queries-{i}.jsonl"
            op = WORK / "output" / f"answers-{i}.jsonl"
            qp.write_text("".join(json.dumps(q, ensure_ascii=False) + "\n" for q in qs))
            os.chown(qp, 0, GID)
            qp.chmod(0o440)
            failure = None
            ps = []
            try:
                call_started = time.monotonic()
                try:
                    run(
                        [
                            "/app/run.sh",
                            "--index-dir",
                            "/work/index",
                            "--queries",
                            str(qp),
                            "--output",
                            str(op),
                        ],
                        f"run-{i}",
                        independent_budget(28800, batches, i - 1),
                    )
                finally:
                    elapsed += time.monotonic() - call_started
                if not op.is_file() or op.is_symlink():
                    raise ValueError("Output is not a regular file")
                ps = completed_rows(op)
            except Exception as exc:
                stop()
                failure = str(exc)
                report["errors"].append(failure)
                if failure.endswith(" timed out"):
                    ps = completed_rows(op)
            dump(LOG / f"run-{i}-completed.json", ps)
            byid = {}
            dups = set()
            for p in ps:
                if not isinstance(p, dict) or not isinstance(p.get("query_id"), str):
                    continue
                key = p["query_id"]
                if key in byid:
                    dups.add(key)
                byid[key] = p
            batch_ids = {q["query_id"] for q in qs}
            unknown = bool(set(byid) - batch_ids)
            for q in qs:
                key = q["query_id"]
                error = None
                value = 0.0
                try:
                    if (
                        (failure and not failure.endswith(" timed out"))
                        or unknown
                        or key in dups
                        or key not in byid
                    ):
                        raise ValueError(
                            "Missing, duplicate, unknown or failed query output"
                        )
                    ids = validate(q, byid[key], pages)
                    value = quality(ids, gold[key], groups[key])
                except (ValueError, OverflowError) as exc:
                    error = str(exc)
                rows.append(
                    {
                        "query_id": key,
                        "domain": groups[key],
                        "value": value,
                        "error": error,
                    }
                )
            predictions.extend(ps)
        report["query_seconds"] = elapsed
        stop()
        value, domains = aggregate(rows)
        report["primary_metric"]["value"] = value
        report["domains"] = domains
        report["queries"] = rows
        report["query_count"] = len(rows)
        report["valid"] = True
        dump(LOG / "predictions.json", predictions)
    except Exception as exc:
        report["errors"].append(type(exc).__name__ + ": " + str(exc))
        if report.get("inputs_verified") and isinstance(
            exc, (ValueError, subprocess.CalledProcessError)
        ):
            report["valid"] = True
    finally:
        stop()
        dump(LOG / "evaluation.json", report)
    print(json.dumps({k: report[k] for k in ["valid", "primary_metric", "errors"]}))
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
