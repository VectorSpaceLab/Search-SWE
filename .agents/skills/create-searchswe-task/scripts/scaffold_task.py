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

TASK_TYPES = {
    "implementation": "create",
    "optimization": "optimize",
}


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


def files_for(task_id: str, hardware: str, mode: str) -> dict[str, str]:
    image = IMAGES[hardware]
    gpus = 1 if hardware == "gpu" else 0
    task_type = TASK_TYPES[mode]
    mode_label = mode.title()
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
            # {task_id}

            **Mode:** {mode_label}

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
            # Task: {task_id}

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
            Replace this scaffold for {task_id} after completing raw-instruction.md.
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
            name = "search-swe/{task_id}"
            version = "0.1.0"
            description = "Replace with the task's observable objective."
            authors = [{{ name = "Search-SWE" }}]
            keywords = ["information-retrieval", "search"]

            [metadata]
            task_type = "{task_type}"
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
        "task_id",
        help="Lowercase task directory name, for example task-1-x-1",
    )
    parser.add_argument(
        "--mode",
        choices=sorted(TASK_TYPES),
        default="implementation",
        help="Engineering mode; defaults to implementation",
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
    parser.add_argument("--submission-first-name", help="Explicit ASCII first name, not a username")
    parser.add_argument("--author", action="append", help="Actual author name; repeat for coauthors (required for submissions)")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not re.fullmatch(r"task-[a-z0-9]+(?:-[a-z0-9]+)*", args.task_id):
        print(
            "error: task_id must match task-<lowercase-segments>",
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
    destination = root / "tasks" / args.task_id
    if args.submission_first_name is not None:
        first_name = args.submission_first_name
        temporary = re.fullmatch(r"task-([12])-x-([1-9][0-9]*)", args.task_id)
        if (not first_name.isascii() or any(c in first_name for c in "/\\.")
                or not temporary):
            print("error: use an ASCII first name and task-<1|2>-x-<positive-ordinal>", file=sys.stderr)
            return 2
        expected_mode = {"1": "implementation", "2": "optimization"}[temporary[1]]
        if args.mode != expected_mode:
            print(f"error: {args.task_id} requires --mode {expected_mode}; hardware is independent", file=sys.stderr)
            return 2
        slug = re.sub(r"[^a-z0-9]+", "-", first_name.lower()).strip("-")
        if not re.fullmatch(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*", slug):
            print("error: provide an ASCII transliteration beginning with a letter", file=sys.stderr)
            return 2
        if not args.author or any(not name.strip() or name.strip().lower() in
                                  ("search-swe", "your name", "author") for name in args.author):
            print("error: submissions require actual --author names", file=sys.stderr)
            return 2
        parent = root / "task-submissions"
        parent.mkdir(exist_ok=True)
        namespace = parent / slug
        if namespace.is_symlink() or (namespace.exists() and not namespace.is_dir()):
            print(f"error: contributor namespace must be a real directory: {namespace}", file=sys.stderr)
            return 2
        namespace.mkdir(exist_ok=True)
        destination = namespace / args.task_id.removeprefix("task-")
    if destination.exists() or destination.is_symlink():
        print(f"error: refusing to overwrite existing path: {destination}", file=sys.stderr)
        return 1

    generated = files_for(args.task_id, args.hardware, args.mode)
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
        f"({args.mode}, {args.hardware})"
    )
    print("Next: replace scaffold text, implement the verifier, add exact assets,")
    print("and follow the skill's references/validation.md through all layers.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
