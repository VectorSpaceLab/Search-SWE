"""Run a package's optional preparation before starting the coding-agent clock."""

import json
from pathlib import Path
import sys
import tempfile

from scripts.evaluation.task_storage import run_command


def prepare_task(task, env, *, cpu_set=None):
    helper = task / "tools/prepare_task.py"
    if not helper.is_file():
        return
    print(f"Preparing {task.name}; this happens before the coding-agent time limit.", flush=True)
    with tempfile.TemporaryDirectory(prefix="search-swe-preparation-") as directory:
        result = Path(directory) / "result.json"
        command = [sys.executable, str(helper), "--result-json", str(result)]
        if cpu_set is not None:
            command += ["--cpu-set", cpu_set]
        code = run_command(command, env, task.parents[1])
        if code:
            raise RuntimeError(f"Task preparation failed for {task.name} (exit {code}); evaluation was not started")
        changes = json.loads(result.read_text())["environment"]
        if not isinstance(changes, dict) or any(
                not isinstance(key, str) or not key or "=" in key or "\0" in key
                or not isinstance(value, str) or "\0" in value for key, value in changes.items()):
            raise ValueError("Task preparation returned invalid environment settings")
        env.update(changes)
