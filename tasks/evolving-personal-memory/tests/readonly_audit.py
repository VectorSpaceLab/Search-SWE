#!/usr/bin/env python3
"""Run three judgments inside the audit role and its inherited Landlock policy."""
import runpy
from pathlib import Path
from landlock_audit import restrict_audit
from rewardkit.agents import CodexBackend
from judge_repeats import run_repeated_judge

# The native read-only bwrap sandbox requires user namespaces, disabled by Docker.
# Landlock protects the role instead; do not loosen host or container namespaces.
original_enter = CodexBackend.__aenter__


async def enter(self):
    result = await original_enter(self)
    if self.codex_home is None:
        raise RuntimeError("Missing isolated Codex home")
    config = self.codex_home / "config.toml"
    # Child tools receive no model credential; /proc is outside the Landlock read set.
    with config.open("a") as f:
        f.write(
            '\n[shell_environment_policy]\ninherit = "all"\nexclude = ["*API_KEY*", "*TOKEN*", "*PASSWORD*", "*SECRET*"]\n'
        )
    return result


CodexBackend.__aenter__ = enter
restrict_audit()
runpy.run_path("/opt/audit/runner.py", run_name="audit_backend")
from rewardkit.__main__ import main

raise SystemExit(run_repeated_judge(main))
