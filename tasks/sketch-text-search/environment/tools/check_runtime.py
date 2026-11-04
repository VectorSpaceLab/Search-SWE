#!/opt/conda/bin/python
"""Run a public build/query under the documented filesystem permissions; no scoring."""
import argparse
import os
from pathlib import Path
import subprocess
import sys


def checked_paths(index_dir, output_file):
    index = Path(index_dir).resolve()
    output = Path(output_file).resolve()
    if index.parent in {Path("/"), Path("/tmp"), Path("/app"), Path("/task")}:
        raise ValueError("Choose an index inside a dedicated check directory, e.g. /work/runtime-check/index.")
    if (index == output.parent or index in output.parent.parents
            or output.parent in index.parents):
        raise ValueError("The writable output directory must not overlap the index directory.")
    return index, output


def prepare_permissions(index_dir, output_file, *, readonly, app=Path("/app")):
    # Validate before changing ownership or permissions, including symlink aliases.
    index, output = checked_paths(index_dir, output_file)
    parent = index.parent
    parent.mkdir(parents=True, exist_ok=True)
    os.chown(parent, 0, 0)
    parent.chmod(0o711)
    index.mkdir(exist_ok=True)
    for path in [index, *index.rglob("*")]:
        if path.is_symlink():
            continue
        executable = bool(path.stat().st_mode & 0o111)
        os.chown(path, 0 if readonly else 10001, 10001)
        if readonly:
            path.chmod(0o550 if path.is_dir() or executable else 0o440)
        else:
            path.chmod(0o750 if path.is_dir() or executable else 0o640)
    output.parent.mkdir(parents=True, exist_ok=True)
    os.chown(output.parent, 10001, 10001)
    output.parent.chmod(0o750)
    home = output.parent if readonly else index
    for name in ["tmp", "cache"]:
        path = home / name
        path.mkdir(exist_ok=True)
        os.chown(path, 10001, 10001)
        path.chmod(0o700)
    # Root can continue editing; the submitted child cannot write /app.
    for path in [app, *app.rglob("*")]:
        if path.is_symlink():
            continue
        executable = bool(path.stat().st_mode & 0o111)
        os.chown(path, 0, 10001)
        path.chmod(0o550 if path.is_dir() or executable else 0o440)
    return index, output, home


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=["build", "query"])
    parser.add_argument("--corpus", default="/task/data/corpus")
    parser.add_argument("--index-dir", default="/work/runtime-check/index")
    parser.add_argument("--queries")
    parser.add_argument("--output", default="/work/runtime-check/output/results.jsonl")
    args = parser.parse_args(argv)
    if os.geteuid() != 0:
        parser.error("Invoke this development-only helper from the root development shell.")
    if args.stage == "query" and not args.queries:
        parser.error("--queries is required for query")
    try:
        index, output, home = prepare_permissions(
            args.index_dir, args.output, readonly=args.stage == "query")
    except ValueError as error:
        parser.error(str(error))
    env = {
        "HOME": str(home), "USER": "submission", "LOGNAME": "submission",
        "PATH": "/opt/conda/bin:/usr/local/bin:/usr/bin:/bin", "LANG": "C.UTF-8",
        "PYTHONUNBUFFERED": "1", "PYTHONDONTWRITEBYTECODE": "1",
        "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1",
        "TMPDIR": str(home / "tmp"), "XDG_CACHE_HOME": str(home / "cache"),
    }
    if os.environ.get("LD_LIBRARY_PATH"):
        env["LD_LIBRARY_PATH"] = os.environ["LD_LIBRARY_PATH"]
    command = ["/app/build.sh", "--corpus", args.corpus, "--index-dir", str(index)]
    if args.stage == "query":
        command = ["/app/run.sh", "--index-dir", str(index), "--queries", args.queries,
                   "--output", str(output)]
    print("Public permission check: uid=10001, code read-only, index parent not writable; "
          "index=" + str(index), file=sys.stderr)
    return subprocess.call(
        ["/usr/bin/setpriv", "--reuid=10001", "--regid=10001", "--clear-groups",
         "--no-new-privs", *command], cwd="/app", env=env)


if __name__ == "__main__":
    raise SystemExit(main())
