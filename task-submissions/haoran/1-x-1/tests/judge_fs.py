"""Run the trajectory judge with a kernel-enforced read-only view."""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sandbox import restrict

read = [
    "/usr",
    "/opt",
    "/bin",
    "/lib",
    "/lib64",
    "/etc",
    "/proc",
    "/dev",
    "/task",
    "/app",
    "/logs/agent",
    "/tests/judge_fs.py",
    "/tests/sandbox.py",
]
# Codex needs API access and temporary/config files. Hidden tests and scoring files remain inaccessible.
restrict(read, ["/logs/verifier/.private", "/tmp", "/dev/null"], allow_network=True)
os.execv("/usr/local/bin/codex", ["/usr/local/bin/codex", *sys.argv[1:]])
