#!/usr/bin/env python3
"""Run the audit as a separate user; keep provider keys in the parent relay."""
import json
import os
import shutil
import signal
import subprocess
import tempfile
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from judge_gateway import JudgeGateway
from prepare_judge import prepare, JUDGE_UID


def main():
    log = Path("/logs/verifier")
    root = Path(tempfile.mkdtemp(prefix="icsi-audit-", dir="/run"))
    process = None
    try:
        model = os.environ.get("TRAJECTORY_JUDGE_MODEL_NAME") or "deepseek-flash"
        with JudgeGateway(os.environ.get("OPENAI_BASE_URL"),
                          os.environ.get("OPENAI_API_KEY"), model) as gateway:
            env = prepare(root, gateway, "/logs/agent/trajectory.json")
            process = subprocess.Popen(
                ["/opt/conda/bin/rewardkit", str(root / "suite"), "--workspace", "/app",
                 "--output", str(root / "out/rewardkit.json"),
                 "--max-concurrent-agent", "1", "--model", model],
                cwd="/app", env=env, user=JUDGE_UID, group=JUDGE_UID,
                extra_groups=[10001], start_new_session=True,
            )
            try:
                status = process.wait(timeout=1400)
            finally:
                subprocess.run(["/usr/bin/pkill", "-KILL", "-u", str(JUDGE_UID)],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if status:
                return status
            for name in ("rewardkit.json", "reward-details.json"):
                source = root / "out" / name
                if source.is_symlink() or not source.is_file():
                    raise ValueError("audit output missing or invalid")
                data = json.loads(source.read_text())
                (log / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
            return 0
    finally:
        if process is not None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
