#!/usr/bin/env python3
"""Run only the trajectory-compliance RewardKit suite."""

import os
import shutil
import subprocess
from pathlib import Path

root = Path("/logs/verifier/.private/rewardkit-suite")
if root.exists():
    shutil.rmtree(root)
root.mkdir(parents=True, mode=0o700)
shutil.copytree("/tests/jailbreak_judge", root / "jailbreak_judge")

raise SystemExit(
    subprocess.call(
        [
            "/opt/conda/bin/rewardkit",
            str(root),
            "--workspace",
            "/app",
            "--output",
            "/logs/verifier/rewardkit.json",
            "--max-concurrent-agent",
            "1",
            "--model",
            os.environ.get("TRAJECTORY_JUDGE_MODEL_NAME") or "deepseek-flash",
        ]
    )
)
