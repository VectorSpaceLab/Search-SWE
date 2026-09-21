"""Confine Codex and descendants to audit inputs and private scratch files."""
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from sandbox import restrict


def main():
    root = Path(os.environ["TASK_JUDGE_ROOT"])
    runtime = ["/usr", "/opt/conda", "/bin", "/lib", "/lib64"]
    read = runtime + [
        "/etc/ld.so.cache", "/etc/localtime", "/etc/ssl", "/etc/passwd",
        "/dev/null", "/dev/urandom", "/dev/random",
        "/task", "/app", str(root / "input"), str(root / "suite"),
        str(root / "helpers"), str(root / "bin"),
    ]
    # No /proc, hidden labels, provider keys or final grading files.
    # Interpreted code inherits this same boundary; /app has no execute grant.
    restrict(read, [str(root / "home"), str(root / "work"), "/dev/null"],
             allow_network=True, execute=runtime + [str(root / "bin")])
    os.execv("/usr/local/bin/codex", ["/usr/local/bin/codex", *sys.argv[1:]])


if __name__ == "__main__":
    main()
