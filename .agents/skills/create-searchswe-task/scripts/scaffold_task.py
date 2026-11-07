#!/usr/bin/env python3
"""Generate a Search-SWE task with a separate grader and trajectory audit."""

from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
import re
import sys
import tomllib


IMAGES = {
    "cpu": "docker.io/hanhainebula/search-swe-base:cpu-py3.12-1.0.0",
    "gpu": "docker.io/hanhainebula/search-swe-base:gpu-cu13.0-py3.12-1.0.0",
}
TASK_NAME = r"(?!all$)(?!task-)[a-z][a-z0-9]*(?:-[a-z0-9]+){0,4}"
TEMPLATES = Path(__file__).resolve().parents[1] / "assets/task"


def target_pins(root: Path) -> dict[str, str]:
    """Read the independent verifier default without executing target code."""
    source = root / "src/search_swe/data/harnesses.toml"
    value = tomllib.loads(source.read_text()).get("verifier", {}).get("codex_version")
    if not isinstance(value, str) or not re.fullmatch(r"\d+\.\d+\.\d+(?:[-+][A-Za-z0-9.-]+)?", value):
        raise ValueError("Target src/search_swe/data/harnesses.toml must define verifier.codex_version")
    return {"CODEX_VERSION": value}


def target_environment(root: Path, hardware: str) -> str:
    """Read the selected checkout's shared image summary as Markdown data."""
    source = root / "docker" / hardware / "environment.md"
    text = source.read_text().strip()
    if not text.startswith(f"# {hardware.upper()} Docker Environment\n"):
        raise ValueError(f"Expected the shared {hardware} environment summary in {source}")
    return text


def files_for(args: argparse.Namespace, pins: dict[str, str], base_environment: str) -> dict[str, str]:
    # These are supervisor allowances, distinct from submission-phase budgets
    # that the contributor must design and enforce inside grader.py.
    judge_supervisor = args.judge_timeout_sec + 300
    verifier_timeout = args.grader_timeout_sec + judge_supervisor + 600
    author_toml = ", ".join("{ name = " + json.dumps(name, ensure_ascii=False) + " }"
                            for name in args.author)
    gpu_reservation = ""
    if args.hardware == "gpu":
        gpu_reservation = """        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
"""
    values = {
        **pins,
        "TASK_NAME": args.task_name,
        "TITLE": args.title or args.task_name.replace("-", " ").title(),
        "AUTHORS_TOML": author_toml,
        "AUTHORS_MD": ", ".join(name.replace("|", "\\|") for name in args.author),
        "DATE": date.today().isoformat(),
        "IMAGE": IMAGES[args.hardware],
        "BASE_ENVIRONMENT": base_environment,
        "GPUS": str(int(args.hardware == "gpu")),
        "GPU_RESERVATION": gpu_reservation,
        "CPUS": str(args.cpus),
        "MEMORY_MB": str(args.memory_mb),
        "STORAGE_MB": str(args.storage_mb),
        "AGENT_TIMEOUT": str(args.agent_timeout_sec),
        "GRADER_TIMEOUT": str(args.grader_timeout_sec),
        "JUDGE_TIMEOUT": str(args.judge_timeout_sec),
        "JUDGE_SUPERVISOR_TIMEOUT": str(judge_supervisor),
        "VERIFIER_TIMEOUT": str(verifier_timeout),
    }
    generated = {}
    for template in sorted(TEMPLATES.rglob("*.tmpl")):
        text = template.read_text()
        for key, value in values.items():
            text = text.replace(f"@@{key}@@", value)
        if re.search(r"@@[A-Z_]+@@", text):
            raise ValueError(f"Unresolved template field in {template.name}")
        generated[template.relative_to(TEMPLATES).as_posix().removesuffix(".tmpl")] = text
    return generated


def positive(value: str) -> int:
    try:
        number = int(value)
        if number > 0:
            return number
    except ValueError:
        pass
    raise argparse.ArgumentTypeError("must be a positive integer")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task_name", help="At most five lowercase hyphen-separated words")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--hardware", choices=sorted(IMAGES), default="cpu")
    parser.add_argument("--author", action="append", required=True, help="Actual author; repeat for coauthors")
    parser.add_argument("--title", help="Readable title shared by README and structured instruction")
    parser.add_argument("--cpus", type=positive, default=8)
    parser.add_argument("--memory-mb", type=positive, default=32768, help="RAM in MiB")
    parser.add_argument("--storage-mb", type=positive, default=102400, help="Storage in MiB")
    parser.add_argument("--agent-timeout-sec", type=positive, default=7200)
    parser.add_argument("--grader-timeout-sec", type=positive, default=1800,
                        help="Whole primary grader supervisor window; derive from submission stages")
    parser.add_argument("--judge-timeout-sec", type=positive, default=900,
                        help="Trajectory Codex session budget; wrapper receives an extra 300 seconds")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not re.fullmatch(TASK_NAME, args.task_name):
        print("error: use at most five lowercase hyphen-separated words; task- and all are reserved", file=sys.stderr)
        return 2
    args.author = [name.strip() for name in args.author]
    if any(not name or name.lower() in ("search-swe", "your name", "author")
           or any(ord(c) < 32 for c in name) for name in args.author):
        print("error: actual single-line --author names are required", file=sys.stderr)
        return 2
    if args.title is not None and (not args.title.strip() or any(ord(c) < 32 for c in args.title)):
        print("error: --title must be a nonempty single line", file=sys.stderr)
        return 2
    root = args.repo_root.resolve()
    if not (root / "tasks").is_dir() or not (root / "docker/README.md").is_file():
        print(f"error: not a Search-SWE repository root: {root}", file=sys.stderr)
        return 2
    if (root / "tasks").is_symlink():
        print("error: task roots must not be symlinks", file=sys.stderr)
        return 2
    destination = root / "tasks" / args.task_name
    if destination.exists() or destination.is_symlink():
        print(f"error: task name already exists; refusing overwrite: {destination}", file=sys.stderr)
        return 1
    try:
        generated = files_for(args, target_pins(root), target_environment(root, args.hardware))
    except (OSError, ValueError, SyntaxError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    destination.mkdir()
    try:
        for relative, content in generated.items():
            path = destination / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        (destination / "tests/test.sh").chmod(0o755)
    except Exception:
        import shutil
        shutil.rmtree(destination, ignore_errors=True)
        raise
    print(f"Created {destination.relative_to(root)} ({args.hardware}, trajectory audit included)")
    print("Next: implement the grader and rubric, finalize inputs/instruction, and record checks in VALIDATION.md.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
