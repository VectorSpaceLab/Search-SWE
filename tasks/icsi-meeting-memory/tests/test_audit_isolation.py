"""Production audit-launcher checks in an explicitly enabled disposable container.

The real run_audit, readonly_audit, Landlock policy and pinned RewardKit backend
run unchanged. Only the external Codex executable is replaced by a local probe;
no model service or real credential is used. The probe checks the generated
shell policy and its filtered environment, not Codex's internal tool scheduler.
"""

import grp
import json
import os
from pathlib import Path
import pwd
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest


TOOL_PROBE = r"""
import json, os
from pathlib import Path
assert os.geteuid() == 10002
assert not any(
    word in key.upper()
    for key in os.environ
    for word in ("API_KEY", "TOKEN", "PASSWORD", "SECRET")
)
assert Path("/audit/trajectory.json").read_text() == '{"steps": []}'
assert json.loads(Path("/audit/submission/memory.json").read_text()) == ["A synthetic note."]
for path in ("/proc/self/environ", "/tests/run_audit.py", OUTSIDE):
    try:
        Path(path).read_bytes()
    except OSError:
        pass
    else:
        raise AssertionError("audit child read forbidden input: " + path)
for path in (
    "/audit/submission/memory.json",
    "/audit/submission/run.sh",
    "/audit/trajectory.json",
    OUTSIDE,
):
    try:
        Path(path).write_text("tampered")
    except OSError:
        pass
    else:
        raise AssertionError("audit child wrote protected input: " + path)
Path("/audit/output/tool-probe.json").write_text(json.dumps({"child_boundary": True}))
"""

CODEX_PROBE = r"""#!/opt/conda/bin/python
import fnmatch, json, os, subprocess, sys, tomllib
from pathlib import Path

if "--version" in sys.argv:
    print("codex-cli 0.164.0")
    raise SystemExit(0)

assert os.geteuid() == 10002
assert sys.argv[1] == "exec"
assert os.environ["OPENROUTER_API_KEY"] == "audit-test-provider-sentinel"
for name in ("OPENAI_API_KEY", "JINA_API_KEY", "ANSWER_JUDGE_API_KEY", "HF_TOKEN"):
    assert name not in os.environ, name
config_path = Path(os.environ["CODEX_HOME"]) / "config.toml"
config_text = config_path.read_text()
assert "audit-test-provider-sentinel" not in config_text
config = tomllib.loads(config_text)
assert config["model_providers"]["openrouter"]["env_key"] == "OPENROUTER_API_KEY"
assert config["model_providers"]["openrouter"]["base_url"] == "https://openrouter.ai/api/v1"
policy = config["shell_environment_policy"]
assert policy["inherit"] == "all"
assert set(policy["exclude"]) == {"*API_KEY*", "*TOKEN*", "*PASSWORD*", "*SECRET*"}
tool_env = {
    key: value for key, value in os.environ.items()
    if not any(fnmatch.fnmatchcase(key, pattern) for pattern in policy["exclude"])
}
tool_code = __TOOL_PROBE__
# Interpreter execution of read-only text is possible; its descendants must
# retain Landlock and the filtered tool environment.
subprocess.run(
    ["/opt/conda/bin/python", "-I", "-c", tool_code],
    env=tool_env, check=True, timeout=10,
)
submitted = Path("/audit/submission/run.sh")
try:
    subprocess.run([str(submitted)], check=True, env=tool_env, timeout=10)
except PermissionError:
    pass
else:
    raise AssertionError("non-executable submission snapshot executed directly")
subprocess.run(
    ["/bin/sh", str(submitted)], env=tool_env, check=True, timeout=10,
)
assert Path("/audit/output/tool-probe.json").is_file()
assert Path("/audit/output/interpreter-probe.json").is_file()
output = Path(sys.argv[sys.argv.index("--output-last-message") + 1])
output.write_text(json.dumps({
    "jailbreak_judge": {"score": "yes", "reasoning": "Synthetic offline boundary probe."},
    "inspection_complete": {"score": "yes", "reasoning": "Synthetic offline boundary probe."},
}))
print(json.dumps({"type": "turn.completed", "usage": {"input_tokens": 0, "output_tokens": 0}}))
"""


@unittest.skipUnless(
    os.environ.get("TASK_ISOLATION_TEST") == "1" and sys.platform == "linux",
    "requires an explicitly enabled disposable Linux verifier container",
)
class ProductionAuditIsolationTests(unittest.TestCase):
    def test_production_launcher_and_inherited_tool_boundary(self):
        self.assertEqual(os.geteuid(), 0)
        self.assertEqual(pwd.getpwnam("audit").pw_uid, 10002)
        self.assertEqual(grp.getgrnam("audit").gr_gid, 10002)
        here = Path(__file__).resolve().parent
        self.assertEqual((here / "run_audit.py").read_bytes(),
                         Path("/tests/run_audit.py").read_bytes())
        dispatch = (here / "test.sh").read_text()
        self.assertIn(
            "/opt/conda/bin/python /tests/run_audit.py "
            "--runner /tests/rewardkit_deepseek.py "
            "--judge deepseek-codex --model deepseek/deepseek-v4.1-flash",
            dispatch,
        )
        self.assertEqual(
            (here / "rewardkit_deepseek.py").read_bytes(),
            Path("/opt/audit/runner.py").read_bytes(),
        )
        for name in ("readonly_audit.py", "landlock_audit.py"):
            self.assertEqual((here / name).read_bytes(), Path("/opt/audit", name).read_bytes())

        audit = Path("/audit")
        # This test owns fixed production paths only in a fresh disposable
        # container. Never remove another test's or an actual run's audit tree.
        self.assertFalse(audit.exists(), "requires a fresh audit directory")
        audit.mkdir(mode=0o750)
        self.addCleanup(shutil.rmtree, audit)
        os.chown(audit, 0, 10002)
        with tempfile.TemporaryDirectory(prefix="audit-boundary-", dir="/run") as temp:
            outside = Path(temp) / "outside.txt"
            Path(temp).chmod(0o755)
            outside.write_text("readable by DAC, excluded by Landlock")
            outside.chmod(0o666)
            tool_probe = TOOL_PROBE.replace("OUTSIDE", repr(str(outside)))
            interpreter_probe = tool_probe.replace("tool-probe.json", "interpreter-probe.json")
            for name, mode, uid in (
                ("submission", 0o550, 0),
                ("config", 0o750, 0),
                ("config/jailbreak_judge", 0o750, 0),
                ("output", 0o700, 10002),
            ):
                path = audit / name
                path.mkdir(mode=mode)
                os.chown(path, uid, 10002)
            for name, content in (
                ("memory.json", '["A synthetic note."]'),
                ("run.sh", "#!/bin/sh\nexec /opt/conda/bin/python -I -c "
                 + shlex.quote(interpreter_probe) + "\n"),
                ("build.sh", "#!/bin/sh\nexit 0\n"),
                ("answer.sh", "#!/bin/sh\nexit 0\n"),
            ):
                path = audit / "submission" / name
                (audit / "submission").chmod(0o750)
                path.write_text(content)
                os.chown(path, 0, 10002)
                path.chmod(0o440)
                (audit / "submission").chmod(0o550)
            trajectory = audit / "trajectory.json"
            trajectory.write_text('{"steps": []}')
            os.chown(trajectory, 0, 10002)
            trajectory.chmod(0o440)
            config = audit / "config/jailbreak_judge/codex.toml"
            shutil.copyfile(here / "jailbreak_judge/codex.toml", config)
            os.chown(config, 0, 10002)
            config.chmod(0o440)
            tmp = Path("/home/audit/tmp")
            tmp.mkdir(mode=0o700, exist_ok=True)
            os.chown(tmp, 10002, 10002)

            binary = Path("/home/audit/.cache/harbor-rewardkit/codex/0.164.0/bin/codex")
            self.assertTrue(binary.is_symlink(), "requires the verifier's pinned Codex link")
            link_target = os.readlink(binary)
            binary.unlink()
            self.addCleanup(lambda: (binary.unlink(), binary.symlink_to(link_target)))
            binary.write_text(CODEX_PROBE.replace("__TOOL_PROBE__", repr(tool_probe)))
            binary.chmod(0o755)
            result = subprocess.run(
                [
                    "/opt/conda/bin/python", "/tests/run_audit.py",
                    "--runner", "/tests/rewardkit_deepseek.py",
                    "--judge", "deepseek-codex",
                    "--model", "deepseek/deepseek-v4.1-flash",
                ],
                env={
                    "PATH": "/opt/conda/bin:/usr/local/bin:/usr/bin:/bin",
                    "OPENAI_BASE_URL": "https://openrouter.ai/api/v1",
                    "OPENAI_API_KEY": "audit-test-provider-sentinel",
                    "JINA_API_KEY": "must-not-reach-audit",
                    "ANSWER_JUDGE_API_KEY": "must-not-reach-audit",
                    "HF_TOKEN": "must-not-reach-audit",
                },
                capture_output=True, text=True, timeout=45,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            for name in ("tool-probe.json", "interpreter-probe.json"):
                self.assertEqual(json.loads((audit / "output" / name).read_text()),
                                 {"child_boundary": True})
            reward = json.loads((audit / "output/reward.json").read_text())
            self.assertTrue(reward, result.stdout + result.stderr)
            self.assertEqual(outside.read_text(), "readable by DAC, excluded by Landlock")
            self.assertEqual((audit / "submission/memory.json").read_text(), '["A synthetic note."]')


if __name__ == "__main__":
    unittest.main()
