#!/usr/bin/env python3
import json, os, shutil, subprocess, time
from pathlib import Path
from evaluation import read_jsonl, validate, quality, aggregate
from batch_runtime import completed_rows, independent_budget

UID = GID = 10001
LOG = Path("/logs/verifier/same-place-image-search-eval")
WORK = Path("/work")
QUERY_PHASE = False


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
    home = "/work/output" if QUERY_PHASE else "/work/index"
    e = {
        "HOME": home,
        "USER": "submission",
        "LOGNAME": "submission",
        "PATH": "/opt/conda/bin:/usr/local/bin:/usr/bin:/bin",
        "LANG": "C.UTF-8",
        "PYTHONUNBUFFERED": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
        "TMPDIR": home + "/tmp",
        "XDG_CACHE_HOME": home + "/cache",
    }
    # Keep the image/runtime's driver selection, including forward compatibility
    # when the host needs it, without exposing the verifier's credentials.
    for k in ["LD_LIBRARY_PATH"]:
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
        "/opt/conda/bin/python",
        "-I",
        "/opt/task-runtime/offline_exec.py",
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
            stdin=subprocess.DEVNULL,
            close_fds=True,
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
        "primary_metric": {"name": "HardPlaceMacroNDCG@5", "value": 0.0},
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
        assert pages
        groups = {
            x["query_id"]: x["group"] for x in read_jsonl("/tests/data/labels.jsonl")
        }
        junk = {
            x["query_id"]: x["junk"] for x in read_jsonl("/tests/data/labels.jsonl")
        }
        assert len({q["query_id"] for q in queries}) == len(queries) and set(gold) == {
            q["query_id"] for q in queries
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
        stop()
        # Freeze the corpus index; each call gets fresh input/output scratch.
        for item in [WORK / "index", *(WORK / "index").rglob("*")]:
            if item.is_symlink():
                continue
            os.chown(item, 0, GID)
            item.chmod(0o550 if item.is_dir() or item.stat().st_mode & 0o111 else 0o440)
        home = Path("/home/submission")
        if home.exists():
            for item in [home, *home.rglob("*")]:
                if item.is_symlink():
                    continue
                os.chown(item, 0, GID)
                item.chmod(0o550 if item.is_dir() else 0o440)
        global QUERY_PHASE
        QUERY_PHASE = True
        batches = [
            queries[: (len(queries) + 1) // 2],
            queries[(len(queries) + 1) // 2 :],
        ]
        assert all(batches)
        for i, qs in enumerate(batches, 1):
            for name in ["input", "output"]:
                folder = WORK / name
                shutil.rmtree(folder)
                folder.mkdir()
                os.chown(folder, 0 if name == "input" else UID, GID)
                folder.chmod(0o750)
            for name in ["tmp", "cache"]:
                folder = WORK / "output" / name
                folder.mkdir()
                os.chown(folder, UID, GID)
                folder.chmod(0o700)
            for item in Path("/dev/shm").iterdir():
                if item.lstat().st_uid == UID:
                    if item.is_dir() and not item.is_symlink():
                        shutil.rmtree(item)
                    else:
                        item.unlink()

            qp = WORK / "input" / f"queries-{i}.jsonl"
            op = WORK / "output" / f"answers-{i}.jsonl"
            public_inputs = []
            for q in qs:
                out = {
                    "query_id": q["query_id"],
                    "exclude_image_ids": q["exclude_image_ids"],
                }
                for field in ["image_path"]:
                    rel = Path(q[field]).relative_to("/private-input")
                    src = Path("/tests/data") / rel
                    dst = WORK / "input" / rel
                    dst.parent.mkdir(exist_ok=True, parents=True)
                    os.chown(dst.parent, 0, GID)
                    dst.parent.chmod(0o750)
                    if not dst.exists():
                        shutil.copyfile(src, dst)
                    os.chown(dst, 0, GID)
                    dst.chmod(0o440)
                    out[field] = str(dst)
                public_inputs.append(out)
            qp.write_text(
                "".join(json.dumps(q, ensure_ascii=False) + "\n" for q in public_inputs)
            )
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
                        independent_budget(5400, batches, i - 1),
                    )
                finally:
                    elapsed += time.monotonic() - call_started
                if not op.is_file() or op.is_symlink():
                    raise ValueError("Output is not a regular file")
                ps = completed_rows(op)
                stop()
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
                    value = quality(ids, gold[key], junk[key])
                except (ValueError, TypeError, OverflowError) as exc:
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
