"""Unprivileged persistent submission; inherited Landlock and seccomp rules."""
import os
from pathlib import Path
import resource
import sys

from confinement import ALL, EXECUTE, READ, READ_DIR, WRITE, confine, restrict_persistent_state


def main():
    runtime = ["/usr", "/bin", "/lib", "/lib64", "/opt/conda", "/etc/ld.so.cache",
               "/etc/localtime", "/proc/cpuinfo", "/proc/meminfo", "/sys/devices/system/cpu"]
    rules = [(p, READ | READ_DIR | EXECUTE) for p in runtime if Path(p).exists()]
    rules += [("/app/submission", READ | READ_DIR | EXECUTE),
              ("/task/public", READ | READ_DIR), ("/work/events", READ | READ_DIR),
              ("/work/state", ALL), ("/dev/null", READ | WRITE), ("/dev/urandom", READ)]
    if Path("/task/reference").exists():
        rules.append(("/task/reference", READ | READ_DIR))
    os.setgroups([])
    os.setgid(10001)
    os.setuid(10001)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_NOFILE, (1024, 1024))
    # Compose's pids_limit covers the complete container. RLIMIT_NPROC would
    # couple the shared submission UID to processes in other concurrent jobs.
    resource.setrlimit(resource.RLIMIT_FSIZE, (32 * 1024**3,) * 2)
    confine(rules)
    restrict_persistent_state()
    os.execvpe("/bin/bash", ["bash", "/app/submission/run.sh"], os.environ)


if __name__ == "__main__":
    main()
