import json, os, shutil, subprocess, time
from pathlib import Path
from evaluation import read_jsonl, evaluate_rows
from batch_runtime import completed_rows

UID = GID = 10001
LOG = Path("/logs/verifier/financial-report-qa-eval")
WORK = Path("/work")


def dump(path, value):
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    )


def stop():
    for signal in ["TERM", "KILL"]:
        subprocess.run(
            ["/usr/bin/pkill", "-" + signal, "-u", "submission"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if signal == "TERM":
            time.sleep(0.2)


def child_env():
    env = {
        "HOME": "/work/index",
        "USER": "submission",
        "LOGNAME": "submission",
        "JAVA_HOME": "/opt/java/openjdk",
        "PATH": "/opt/conda/bin:/opt/java/openjdk/bin:/usr/local/bin:/usr/bin:/bin",
        "LANG": "C.UTF-8",
        "PYTHONUNBUFFERED": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "TMPDIR": "/work/index/tmp",
        "XDG_CACHE_HOME": "/work/index/cache",
    }
    for key in [
        "OPENROUTER_API_KEY",
        "JINA_API_KEY",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "NO_PROXY",
        "http_proxy",
        "https_proxy",
        "no_proxy",
    ]:
        if os.environ.get(key):
            env[key] = os.environ[key]
    return env


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
    begin = time.monotonic()
    with (
        (LOG / (label + ".stdout.log")).open("wb") as out,
        (LOG / (label + ".stderr.log")).open("wb") as err,
    ):
        process = subprocess.Popen(
            command(args),
            cwd="/app",
            env=child_env(),
            stdout=out,
            stderr=err,
            start_new_session=True,
        )
        try:
            code = process.wait(timeout=timeout)
            timed_out = False
        except subprocess.TimeoutExpired:
            stop()
            process.wait(timeout=5)
            code = 124
            timed_out = True
    return {
        "label": label,
        "seconds": time.monotonic() - begin,
        "returncode": code,
        "timed_out": timed_out,
        "timeout_seconds": timeout,
    }


def main():
    LOG.mkdir(parents=True, exist_ok=True)
    report = {
        "valid": False,
        "errors": [],
        "primary_metric": {"name": "EvidenceRecall@5", "value": 0.0},
    }
    try:
        if os.environ.get("SEARCH_SWE_EXECUTION_ERROR"):
            raise ValueError(os.environ["SEARCH_SWE_EXECUTION_ERROR"])
        queries = read_jsonl("/tests/data/queries.jsonl")
        labels = {r["query_id"]: r for r in read_jsonl("/tests/data/labels.jsonl")}
        if (
            not queries
            or len({q["query_id"] for q in queries}) != len(queries)
            or set(labels) != {q["query_id"] for q in queries}
        ):
            raise ValueError("Private query/label mismatch")
        if any(set(q) != {"query_id", "question"} for q in queries):
            raise ValueError("Unexpected query fields")
        if WORK.exists():
            shutil.rmtree(WORK)
        WORK.mkdir(mode=0o711)
        WORK.chmod(0o711)
        for name in ["corpus", "input", "index", "output"]:
            path = WORK / name
            path.mkdir()
            os.chown(path, 0 if name in ["corpus", "input"] else UID, GID)
            path.chmod(0o750)
        for name in ["tmp", "cache"]:
            path = WORK / "index" / name
            path.mkdir(mode=0o700)
            os.chown(path, UID, GID)
        corpus = WORK / "corpus/reports.jsonl"
        shutil.copyfile("/tests/corpus/reports.jsonl", corpus)
        os.chown(corpus, 0, GID)
        corpus.chmod(0o440)
        documents = {r["document_id"]: r["text"] for r in read_jsonl(corpus)}
        if len(documents) != 885:
            raise ValueError("Expected the complete 885-report corpus")
        checks = " && ".join(
            [
                "test -x /app/build.sh",
                "test -x /app/run.sh",
                "test -r /work/corpus/reports.jsonl",
                "test ! -r /tests/data/queries.jsonl",
                "test ! -r /tests/data/labels.jsonl",
                "test ! -r /tests/grader.py",
                "test ! -r /logs/agent/trajectory.json",
                "test ! -w /logs/verifier",
                "test ! -w /app",
                'test -z "${OPENAI_API_KEY+x}"',
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
        build = run(
            ["/app/build.sh", "--corpus", "/work/corpus", "--index-dir", "/work/index"],
            "build",
            1800,
        )
        report["build"] = build
        if build["returncode"] != 0:
            raise ValueError("Index construction failed or timed out")
        predictions = []
        executions = []
        mid = (len(queries) + 1) // 2
        for i, qs in enumerate([queries[:mid], queries[mid:]], 1):
            if not qs:
                continue
            query_path = WORK / "input" / f"queries-{i}.jsonl"
            output_path = WORK / "output" / f"results-{i}.jsonl"
            query_path.write_text(
                "".join(json.dumps(q, ensure_ascii=False) + "\n" for q in qs)
            )
            os.chown(query_path, 0, GID)
            query_path.chmod(0o440)
            execution = run(
                [
                    "/app/run.sh",
                    "--index-dir",
                    "/work/index",
                    "--queries",
                    str(query_path),
                    "--output",
                    str(output_path),
                ],
                f"run-{i}",
                3600,
            )
            if execution["returncode"] == 0 or execution["timed_out"]:
                rows = completed_rows(output_path)
                allowed = {q["query_id"] for q in qs}
                rows = [
                    row
                    for row in rows
                    if isinstance(row.get("query_id"), str)
                    and row["query_id"] in allowed
                ]
                predictions.extend(rows)
                execution["completed_rows"] = len(rows)
            else:
                execution["completed_rows"] = 0
            executions.append(execution)
        stop()
        score, details = evaluate_rows(queries, predictions, labels, documents)
        report.update(
            valid=True,
            query_count=len(queries),
            report_count=len(documents),
            query_executions=executions,
            queries=details,
        )
        report["primary_metric"]["value"] = score
        dump(LOG / "retrieved-spans.json", predictions)
    except Exception as exc:
        report["errors"].append(type(exc).__name__ + ": " + str(exc))
    finally:
        stop()
        dump(LOG / "evaluation.json", report)
    print(
        json.dumps({key: report[key] for key in ["valid", "primary_metric", "errors"]})
    )
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
