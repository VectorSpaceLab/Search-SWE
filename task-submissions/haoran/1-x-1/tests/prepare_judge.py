"""Prepare a separate, unprivileged trajectory-audit workspace."""
import json
import os
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
JUDGE_UID = 10002


def prepare(root, gateway, trajectory):
    root = Path(root)
    for name in ("bin", "home", "work", "out", "input", "suite", "helpers"):
        (root / name).mkdir()
    shutil.copyfile(trajectory, root / "input/trajectory.json")
    for name in ("sandbox.py", "judge_fs.py"):
        shutil.copyfile(HERE / name, root / "helpers" / name)
    shutil.copytree(HERE / "jailbreak_judge", root / "suite/jailbreak_judge")
    rule = root / "suite/jailbreak_judge/codex.toml"
    rule.write_text(rule.read_text().replace("/logs/agent/trajectory.json", str(root / "input/trajectory.json")))
    wrapper = root / "bin/codex"
    wrapper.write_text(f'#!/bin/sh\nexec /opt/conda/bin/python -I {root}/helpers/judge_fs.py "$@"\n')
    wrapper.chmod(0o755)
    config = (
        'model_provider = "trajectory_judge"\napproval_policy = "never"\n'
        'sandbox_mode = "danger-full-access"\n'
        '[model_providers.trajectory_judge]\nname = "Trajectory judge"\n'
        f'base_url = {json.dumps(gateway.url)}\n'
        'wire_api = "responses"\nenv_key = "OPENAI_API_KEY"\nsupports_websockets = false\n'
    )
    (root / "home/config.toml").write_text(config)
    os.chown(root, 0, JUDGE_UID)
    root.chmod(0o750)
    for p in root.rglob("*"):
        os.chown(p, 0, JUDGE_UID)
        p.chmod(0o750 if p.is_dir() or p == wrapper else 0o640)
    for name in ("home", "work", "out"):
        os.chown(root / name, JUDGE_UID, JUDGE_UID)
        (root / name).chmod(0o700)
    return {
        "PATH": f"{root}/bin:/opt/conda/bin:/usr/local/bin:/usr/bin:/bin",
        "HOME": str(root / "home"), "CODEX_HOME": str(root / "home"),
        "TMPDIR": str(root / "work"), "LANG": "C.UTF-8",
        "PYTHONNOUSERSITE": "1", "PYTHONDONTWRITEBYTECODE": "1",
        "LITELLM_LOCAL_MODEL_COST_MAP": "True",
        "OPENAI_BASE_URL": gateway.url, "OPENAI_API_KEY": gateway.token,
        "TASK_JUDGE_ROOT": str(root),
    }
