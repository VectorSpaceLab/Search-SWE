#!/usr/bin/env python3
"""Create a fail-closed Search-SWE task skeleton without overwriting files."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
import textwrap


IMAGES = {
    "cpu": "docker.io/hanhainebula/search-swe-base:cpu-py3.12-1.0.0",
    "gpu": "docker.io/hanhainebula/search-swe-base:gpu-cu13.0-py3.12-1.0.0",
}

TASK_NAME = r"(?!all$)(?!task-)[a-z][a-z0-9]*(?:-[a-z0-9]+){0,4}"


def clean(text: str) -> str:
    return textwrap.dedent(text).lstrip("\n").rstrip() + "\n"


def compose(hardware: str, *, environment: bool) -> str:
    gpu = ""
    if hardware == "gpu":
        gpu = clean(
            """
                deploy:
                  resources:
                    reservations:
                      devices:
                        - driver: nvidia
                          count: 1
                          capabilities: [gpu]
            """
        )
    volumes = ""
    if environment:
        volumes = clean(
            """
                volumes:
                  - type: bind
                    source: ./docs
                    target: /task/docs
                    read_only: true
                    bind:
                      create_host_path: false
            """
        )
    body = "services:\n  main:\n"
    body += textwrap.indent(gpu, "    ") if gpu else ""
    body += textwrap.indent(volumes, "    ") if volumes else ""
    if not gpu and not volumes:
        body += "    {}\n"
    return body


def files_for(task_name: str, hardware: str) -> dict[str, str]:
    image = IMAGES[hardware]
    gpus = 1 if hardware == "gpu" else 0
    return {
        ".gitignore": clean(
            """
            /data/
            /models/
            __pycache__/
            *.py[cod]
            """
        ),
        "README.md": clean(
            f"""
            # {task_name}

            **Task:** `{task_name}`

            Replace this scaffold text with an author-facing overview of the
            objective, dataset/model provenance and license, metric, resource
            needs, and local validation procedure.
            """
        ),
        "assets.json": json.dumps(
            {"schema_version": 1, "files": []}, indent=2
        )
        + "\n",
        "raw-instruction.md": clean(
            f"""
            # Task: {task_name}

            ## Task Description

            Replace this text with the task goal and starting state.

            ## Requirements

            Specify exact paths, interfaces, formats, constraints, and files
            that may or may not be modified.

            ## Available Validation Data

            Describe only agent-visible examples and a practical self-check.

            ## Environment and Available Resources

            Point to `/task/docs/environment.md` and, when applicable,
            `/task/docs/available_resources.md`.

            ## Expected Artifacts

            Define every required output path, permission, and invocation.

            ## Verification

            Describe graded behavior at a high level without exposing hidden
            answers or implementation details.

            ## Hidden Test Overview

            Summarize covered scenarios without revealing hidden inputs,
            labels or reference outputs. State public performance gates in
            Requirements instead of hiding them from the agent.
            """
        ),
        "instruction.md": clean(
            f"""
            Replace this scaffold for {task_name} after completing raw-instruction.md.
            Write a direct natural-language request describing the task, current
            data and starting system, resources, constraints, acceptance criteria,
            and optimization objective. Omit self-introductions, invented people,
            roles, and fictional scenes. Use connected prose paragraphs without
            headings, lists, tables, or fenced blocks. Preserve every source
            condition and exact interface; follow references/instruction-rewrite.md
            in the authoring skill and remove this author-only prompt before use.
            """
        ),
        "task.toml": clean(
            f"""
            schema_version = "1.4"

            artifacts = [
                "/app",
            ]

            [task]
            name = "search-swe/{task_name}"
            version = "0.1.0"
            description = "Replace with the task's observable objective."
            authors = [{{ name = "Search-SWE" }}]
            keywords = ["information-retrieval", "search"]

            [metadata]
            primary_metric = "Replace with the primary metric"

            [agent]
            timeout_sec = 7200.0
            user = "root"
            network_mode = "no-network"

            [verifier]
            timeout_sec = 3600.0
            user = "root"
            environment_mode = "separate"
            network_mode = "no-network"

            [environment]
            build_timeout_sec = 1800.0
            workdir = "/app"
            os = "linux"
            network_mode = "no-network"
            cpus = 8
            memory_mb = 32768
            storage_mb = 102400
            gpus = {gpus}
            """
        ),
        "environment/Dockerfile": clean(
            f"""
            FROM {image}

            RUN mkdir -p /app /task/data /task/docs /logs
            """
        ),
        "environment/docker-compose.yaml": compose(
            hardware, environment=True
        ),
        "environment/docs/environment.md": clean(
            f"""
            # Environment

            This is a {hardware.upper()} task based on `{image}`.

            Replace this text with the exact task-visible runtime, commands,
            installed additions, paths, and hardware capabilities.
            """
        ),
        "environment/docs/available_resources.md": clean(
            """
            # Available Resources

            The scaffold declares no external API resources. If the task needs
            one, document only the injected endpoints, model allowlists,
            environment-variable names, and usage restrictions. Never include
            credential values.
            """
        ),
        "tests/.dockerignore": clean(
            """
            __pycache__/
            *.py[cod]
            """
        ),
        "tests/Dockerfile": clean(
            f"""
            FROM {image}

            RUN useradd --create-home --uid 10001 --user-group submission

            COPY . /tests/

            RUN chmod 700 /tests \\
                && chmod 700 /tests/test.sh
            """
        ),
        "tests/docker-compose.yaml": compose(hardware, environment=False),
        "tests/test.sh": clean(
            r"""
            #!/usr/bin/env bash
            set -u

            reward_dir=/logs/verifier
            mkdir -p "$reward_dir"
            printf '0\n' > "$reward_dir/reward.txt"
            printf '%s\n' \
              'Verifier scaffold is intentionally fail-closed; implement it.' >&2
            exit 1
            """
        ),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "task_name",
        help="Descriptive lowercase task name, at most five hyphen-separated words",
    )
    parser.add_argument(
        "--hardware",
        choices=sorted(IMAGES),
        default="cpu",
        help="Task hardware class; defaults to cpu",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path.cwd(),
        help="Search-SWE repository root; defaults to the current directory",
    )
    parser.add_argument("--formal", action="store_true", help="Maintainer-only scaffold under tasks/; default is task-submissions/")
    parser.add_argument("--author", action="append", required=True, help="Actual author name; repeat for coauthors")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not re.fullmatch(TASK_NAME, args.task_name):
        print(
            "error: use at most five lowercase hyphen-separated words, without a task- prefix; all is reserved",
            file=sys.stderr,
        )
        return 2

    root = args.repo_root.resolve()
    if not (root / "tasks").is_dir() or not (root / "docker/README.md").is_file():
        print(f"error: not a Search-SWE repository root: {root}", file=sys.stderr)
        return 2

    if (root / "tasks").is_symlink() or (root / "task-submissions").is_symlink():
        print("error: task roots must not be symlinks", file=sys.stderr)
        return 2
    if any(not name.strip() or name.strip().lower() in
           ("search-swe", "your name", "author") for name in args.author):
        print("error: actual --author names are required", file=sys.stderr)
        return 2
    for directory in ("tasks", "task-submissions"):
        existing = root / directory / args.task_name
        if existing.exists() or existing.is_symlink():
            print(f"error: task name already exists; refusing overwrite: {existing}", file=sys.stderr)
            return 1
    parent = root / ("tasks" if args.formal else "task-submissions")
    parent.mkdir(exist_ok=True)
    destination = parent / args.task_name

    generated = files_for(args.task_name, args.hardware)
    if args.author:
        authors = ", ".join('{ name = ' + json.dumps(name.strip(), ensure_ascii=False) + ' }'
                            for name in args.author)
        generated["task.toml"] = generated["task.toml"].replace(
            'authors = [{ name = "Search-SWE" }]', f"authors = [{authors}]")
    # Reserve the directory before writing; never merge into an existing task.
    destination.mkdir()
    try:
        for relative, content in generated.items():
            path = destination / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        (destination / "tests/test.sh").chmod(0o755)
    except Exception:
        # The destination did not exist before this invocation, so a failed
        # scaffold should not leave a misleading partial task behind.
        import shutil

        shutil.rmtree(destination, ignore_errors=True)
        raise

    print(
        f"Created {destination.relative_to(root)} "
        f"({args.hardware})"
    )
    print("Next: replace scaffold text, implement the verifier, add exact assets,")
    print("and follow the skill's references/validation.md through all layers.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
