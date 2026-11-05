#!/usr/bin/env python3
import argparse, hashlib, os, subprocess
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument("--runner", required=True)
p.add_argument("--judge", choices=["deepseek-codex"], required=True)
p.add_argument("--model", choices=["deepseek/deepseek-v4.1-flash"], required=True)
a = p.parse_args()
if (
    Path(a.runner).resolve() != Path("/tests/rewardkit_deepseek.py")
    or hashlib.sha256(Path(a.runner).read_bytes()).digest()
    != hashlib.sha256(Path("/opt/audit/runner.py").read_bytes()).digest()
):
    raise RuntimeError("Pinned audit backend mismatch")
env = {
    "HOME": "/home/audit",
    "USER": "audit",
    "LOGNAME": "audit",
    "PATH": "/opt/conda/bin:/usr/local/bin:/usr/bin:/bin",
    "LANG": "C.UTF-8",
    "TMPDIR": "/home/audit/tmp",
    "REWARDKIT_LOG_DIR": "/audit/output/native",
    "LITELLM_LOCAL_MODEL_COST_MAP": "true",
    "OPENAI_BASE_URL": os.environ["OPENAI_BASE_URL"],
    "OPENAI_API_KEY": os.environ["OPENAI_API_KEY"],
}
args = [
    "/usr/sbin/runuser",
    "--preserve-environment",
    "-u",
    "audit",
    "--",
    "/usr/bin/setpriv",
    "--no-new-privs",
    "/opt/conda/bin/python",
    "/opt/audit/readonly_audit.py",
    "/audit/config",
    "--workspace",
    "/app/submission",
    "--output",
    "/audit/output/audit.json",
    "--max-concurrent-agent",
    "1",
    "--judge",
    "deepseek-codex",
    "--model",
    "deepseek/deepseek-v4.1-flash",
]
raise SystemExit(subprocess.run(args, env=env, cwd="/home/audit").returncode)
