#!/usr/bin/env python3
import json, os, shutil, subprocess, time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from evaluation import (
    jsonl,
    corpus,
    check_retrieval,
    answer_request,
    check_answer,
    fama,
)
from semantic_panel import Panel
from batch_runtime import completed_rows

WORK = Path("/work")
LOG = Path("/logs/verifier/evolving-personal-memory-eval")
UID = GID = 10001
ANSWER_SLOTS = 8
ANSWER_TOTAL_SECONDS = 7200
ANSWER_QUERY_SECONDS = 600


class SubmissionError(ValueError):
    pass


def dump(path, value):
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    )


def stop_user(name):
    for signal in ["TERM", "KILL"]:
        subprocess.run(
            ["/usr/bin/pkill", "-" + signal, "-u", name],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if signal == "TERM":
            time.sleep(0.1)


def command(user, args):
    return [
        "/usr/sbin/runuser",
        "--preserve-environment",
        "-u",
        user,
        "--",
        "/usr/bin/setpriv",
        "--no-new-privs",
        *args,
    ]


def child_env(home, answer=False):
    values = {
        "HOME": str(home),
        "USER": "answer" if answer else "submission",
        "LOGNAME": "answer" if answer else "submission",
        "JAVA_HOME": "/opt/java/openjdk",
        "PATH": "/opt/conda/bin:/opt/java/openjdk/bin:/usr/local/bin:/usr/bin:/bin",
        "LANG": "C.UTF-8",
        "PYTHONUNBUFFERED": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "TMPDIR": str(home),
        "XDG_CACHE_HOME": str(home / "cache"),
    }
    allowed = [
        "OPENROUTER_API_KEY",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "NO_PROXY",
        "http_proxy",
        "https_proxy",
        "no_proxy",
    ]
    if not answer:
        allowed.append("JINA_API_KEY")
    for key in allowed:
        if os.environ.get(key):
            values[key] = os.environ[key]
    return values


def run(args, label, timeout, user="submission", env=None, cwd="/app"):
    start = time.monotonic()
    with (
        (LOG / (label + ".stdout.log")).open("wb") as out,
        (LOG / (label + ".stderr.log")).open("wb") as err,
    ):
        process = subprocess.Popen(
            command(user, args),
            cwd=cwd,
            env=env or child_env(WORK / "index/tmp"),
            stdin=subprocess.DEVNULL,
            stdout=out,
            stderr=err,
            start_new_session=True,
        )
        try:
            code = process.wait(timeout=timeout)
            timed_out = False
        except subprocess.TimeoutExpired:
            stop_user(user)
            process.wait(timeout=5)
            code = 124
            timed_out = True
    return {
        "label": label,
        "seconds": time.monotonic() - start,
        "returncode": code,
        "timed_out": timed_out,
        "timeout_seconds": timeout,
    }


def stop_all():
    stop_user("submission")
    for slot in range(1, ANSWER_SLOTS + 1):
        stop_user("answer" + str(slot))


def answer_one(index, query, ids, records, slot, remaining):
    user = "answer" + str(slot)
    uid = 11000 + slot
    request_dir = WORK / "answers" / ("request-" + str(index))
    request_dir.mkdir(mode=0o750)
    os.chown(request_dir, 0, uid)
    request_dir.chmod(0o750)
    output_dir = request_dir / "output"
    temp = request_dir / "tmp"
    for path in [output_dir, temp]:
        path.mkdir(mode=0o700)
        os.chown(path, uid, uid)
    request = request_dir / "request.json"
    output = output_dir / "answer.json"
    payload = answer_request(query, ids, records)
    dump(request, payload)
    os.chown(request, 0, uid)
    request.chmod(0o440)
    execution = run(
        [
            "/opt/conda/bin/python",
            "/opt/answer/sandbox.py",
            str(request),
            str(output),
            str(temp),
        ],
        "answer-" + str(index),
        min(ANSWER_QUERY_SECONDS, remaining),
        user=user,
        env=child_env(temp, answer=True),
        cwd=str(temp),
    )
    stop_user(user)
    answer = None
    try:
        if execution["returncode"] != 0:
            raise ValueError("Answer command failed or timed out")
        if output.is_symlink() or not output.is_file():
            raise ValueError("Missing answer output")
        answer = check_answer(query, json.loads(output.read_text()))
    except (ValueError, OSError) as exc:
        execution["error"] = str(exc)
    execution.update(
        input_record_count=len(ids),
        input_text_characters=sum(len(records[i]["text"]) for i in ids),
        input_json_bytes=request.stat().st_size,
        answer_user=user,
    )
    # Retain source material and outputs privately after the role has stopped.
    private = LOG / "answer-inputs"
    private.mkdir(mode=0o700, exist_ok=True)
    shutil.copyfile(request, private / (str(index) + ".json"))
    if output.is_file() and not output.is_symlink():
        shutil.copyfile(output, private / (str(index) + "-output.json"))
    shutil.rmtree(request_dir)
    return answer, execution


def main():
    LOG.mkdir(parents=True, exist_ok=True)
    report = {
        "valid": False,
        "semantic_judge_succeeded": False,
        "errors": [],
        "primary_metric": {"name": "FAMA", "value": 0.0},
    }
    predictions = []
    retrievals = []
    answer_runs = []
    bad = {}
    try:
        if os.environ.get("SEARCH_SWE_EXECUTION_ERROR"):
            raise SubmissionError(os.environ["SEARCH_SWE_EXECUTION_ERROR"])
        qs = jsonl("/tests/data/queries.jsonl")
        labels = {g["query_id"]: g for g in jsonl("/tests/data/labels.jsonl")}
        records = corpus("/private-corpus/records.jsonl")
        if len(qs) != 595 or len(labels) != 595 or len(records) != 27614:
            raise ValueError("Unexpected fixed input counts")
        if any(type(r["session_id"]) is not int for r in records.values()) or any(
            type(q["cutoff_session"]) is not int for q in qs
        ):
            raise ValueError("Session IDs and cutoffs must be integers")
        if WORK.exists():
            shutil.rmtree(WORK)
        WORK.mkdir(mode=0o711)
        WORK.chmod(0o711)
        for name in ["corpus", "input", "index", "output", "answers"]:
            path = WORK / name
            path.mkdir()
            os.chown(
                path,
                UID if name in ["index", "output"] else 0,
                GID if name != "answers" else 0,
            )
            path.chmod(
                0o700
                if name in ["index", "output"]
                else 0o711 if name == "answers" else 0o750
            )
        temp = WORK / "index/tmp"
        temp.mkdir(mode=0o700)
        os.chown(temp, UID, GID)
        path = WORK / "corpus/records.jsonl"
        shutil.copyfile("/private-corpus/records.jsonl", path)
        os.chown(path, 0, GID)
        path.chmod(0o440)
        for script in ["build.sh", "search.sh", "answer.sh"]:
            path = Path("/app") / script
            if not path.is_file() or path.is_symlink() or not os.access(path, os.X_OK):
                raise SubmissionError("Missing or invalid executable " + script)
        checks = " && ".join(
            [
                "test -r /work/corpus/records.jsonl",
                "test ! -r /tests/data/labels.jsonl",
                "test ! -r /private-corpus/records.jsonl",
                "test ! -r /logs/agent/trajectory.json",
                "test ! -w /logs/verifier",
                "test ! -w /app",
                'test -z "${OPENAI_API_KEY+x}"',
                'test -z "${MEMORA_JUDGE_API_KEY+x}"',
                "test ! -r /proc/1/environ",
            ]
        )
        subprocess.run(
            command("submission", ["/bin/sh", "-c", checks]),
            check=True,
            env=child_env(temp),
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
            raise SubmissionError("Index construction failed or timed out")
        mid = (len(qs) + 1) // 2
        search_runs = []
        valid_ids = {}
        for i, subset in enumerate([qs[:mid], qs[mid:]], 1):
            query_path = WORK / "input" / f"queries-{i}.jsonl"
            output_path = WORK / "output" / f"retrieved-{i}.jsonl"
            query_path.write_text(
                "".join(json.dumps(q, ensure_ascii=False) + "\n" for q in subset)
            )
            os.chown(query_path, 0, GID)
            query_path.chmod(0o440)
            execution = run(
                [
                    "/app/search.sh",
                    "--index-dir",
                    "/work/index",
                    "--queries",
                    str(query_path),
                    "--output",
                    str(output_path),
                ],
                "search-" + str(i),
                1800,
            )
            rows = (
                completed_rows(output_path)
                if execution["returncode"] == 0 or execution["timed_out"]
                else []
            )
            counts = {}
            byid = {}
            for row in rows:
                k = row.get("query_id")
                if isinstance(k, str):
                    counts[k] = counts.get(k, 0) + 1
                    byid[k] = row
            for q in subset:
                k = q["query_id"]
                try:
                    if counts.get(k) != 1:
                        raise ValueError("Missing or duplicate retrieval result")
                    valid_ids[k] = check_retrieval(q, byid[k], records)
                    retrievals.append(byid[k])
                except ValueError as exc:
                    bad[k] = str(exc)
            search_runs.append(execution)
        # No retrieval process survives into answering, including build services.
        stop_user("submission")
        report["search_runs"] = search_runs
        dump(LOG / "retrievals.json", retrievals)
        started = time.monotonic()
        deadline = started + ANSWER_TOTAL_SECONDS
        jobs = [(i, q) for i, q in enumerate(qs) if q["query_id"] in valid_ids]

        def worker(slot, assigned):
            local_answers = []
            local_runs = []
            local_errors = {}
            for index, q in assigned:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    local_errors[q["query_id"]] = "Answer phase deadline reached"
                    continue
                answer, execution = answer_one(
                    index, q, valid_ids[q["query_id"]], records, slot, remaining
                )
                local_runs.append(execution)
                if answer:
                    local_answers.append(answer)
                else:
                    local_errors[q["query_id"]] = execution.get(
                        "error", "Invalid answer"
                    )
            return local_answers, local_runs, local_errors

        with ThreadPoolExecutor(max_workers=ANSWER_SLOTS) as pool:
            futures = [
                pool.submit(worker, slot, jobs[slot - 1 :: ANSWER_SLOTS])
                for slot in range(1, ANSWER_SLOTS + 1)
            ]
            for future in as_completed(futures):
                answers, runs, errors = future.result()
                predictions.extend(answers)
                answer_runs.extend(runs)
                bad.update(errors)
                dump(LOG / "predictions.json", predictions)
                dump(LOG / "answer-runs.json", answer_runs)
        stop_all()
        report["answer_seconds"] = time.monotonic() - started
        report["answer_isolation"] = (
            "Distinct answer UIDs, current-request Landlock allowlist, read-only answer code, no corpus/index/cache/prior requests"
        )
        pm = {p["query_id"]: p for p in predictions}
        valid_qs = [q for q in qs if q["query_id"] in pm]
        votes = {}
        if valid_qs:
            panel = Panel()
            begin = time.monotonic()
            votes = panel.evaluate(valid_qs, pm, labels)
            report.update(
                semantic_judge_seconds=time.monotonic() - begin,
                semantic_judge_models=panel.models,
                semantic_judge_calls=panel.calls,
                semantic_judge_retries=panel.retries,
            )
        else:
            report.update(semantic_judge_calls=0, semantic_judge_required=False)
        report["semantic_judge_succeeded"] = True
        scores = []
        cells = {}
        for q in qs:
            k = q["query_id"]
            g = labels[k]
            score = 0.0
            detail = {}
            if k in votes:
                score, detail = fama(g, votes[k])
            cell = g["task_type"] + "/" + g["horizon"]
            cells.setdefault(cell, []).append(score)
            scores.append(
                {
                    "query_id": k,
                    "fama": score,
                    "task_type": g["task_type"],
                    "horizon": g["horizon"],
                    "error": bad.get(k),
                    **detail,
                    "votes": votes.get(k),
                }
            )
        report.update(
            valid=True,
            query_count=len(qs),
            completed_query_count=len(predictions),
            queries=scores,
            per_task_horizon={k: sum(v) / len(v) for k, v in cells.items()},
            cell_counts={k: len(v) for k, v in cells.items()},
        )
        report["primary_metric"]["value"] = sum(row["fama"] for row in scores) / len(qs)
    except SubmissionError as exc:
        report.update(
            valid=True,
            semantic_judge_succeeded=True,
            semantic_judge_required=False,
            semantic_judge_calls=0,
            query_count=len(qs),
            completed_query_count=0,
        )
        report["errors"].append("SubmissionError: " + str(exc))
    except Exception as exc:
        report["errors"].append(type(exc).__name__ + ": " + str(exc))
    finally:
        stop_all()
        dump(LOG / "predictions.json", predictions)
        dump(LOG / "answer-runs.json", answer_runs)
        dump(LOG / "evaluation.json", report)
    print(
        json.dumps(
            {
                key: report[key]
                for key in [
                    "valid",
                    "semantic_judge_succeeded",
                    "primary_metric",
                    "errors",
                ]
            }
        )
    )
    return 0 if report["valid"] and report["semantic_judge_succeeded"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
