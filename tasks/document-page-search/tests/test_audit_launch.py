"""Exercise the production audit chain in an explicit disposable container."""
import ctypes
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import unittest

ENABLED = os.environ.get("SEARCH_SWE_AUDIT_LAUNCH_TEST") == "1"

FAKE_CODEX = r'''#!/opt/conda/bin/python
import ctypes, json, os, sys, tomllib
from pathlib import Path
if "--version" in sys.argv:
    print("codex-cli 0.164.0")
    raise SystemExit(0)
config = json.loads(Path("/opt/audit/fixture.json").read_text())
state_path = Path("/audit/output/fixture-calls.json")
state = json.loads(state_path.read_text()) if state_path.exists() else {"homes": [], "calls": []}
home = os.environ["CODEX_HOME"]
if home not in state["homes"]:
    state["homes"].append(home)
number = state["homes"].index(home) + 1
checks = {"uid": os.getuid(), "no_new_privs": ctypes.CDLL(None).prctl(39, 0, 0, 0, 0)}
for name, path in {"tests": "/tests/private-marker", "app": "/app/note.txt", "logs": "/logs/verifier/private-marker", "proc": "/proc/self/environ"}.items():
    try:
        Path(path).read_bytes()
        checks[name + "_denied"] = False
    except PermissionError:
        checks[name + "_denied"] = True
try:
    Path("/audit/submission/forbidden-write").write_text("denied")
    checks["snapshot_write_denied"] = False
except PermissionError:
    checks["snapshot_write_denied"] = True
checks["snapshot_readable"] = Path("/audit/submission/note.txt").read_text() == "provided source"
policy = tomllib.loads((Path(home) / "config.toml").read_text())["shell_environment_policy"]
checks["credential_filter"] = all(x in policy["exclude"] for x in ["*API_KEY*", "*TOKEN*", "*PASSWORD*", "*SECRET*"])
checks["provider_key_mapped"] = bool(os.environ.get("OPENROUTER_API_KEY")) and "CODEX_API_KEY" not in os.environ
checks["judgment"] = number
state["calls"].append(checks)
state_path.write_text(json.dumps(state))
if config.get("fail_judgment") == number:
    print(json.dumps({"type": "turn.failed", "error": {"message": "offline transport failure"}}))
    raise SystemExit(1)
verdict = config["verdicts"][number - 1]
args = sys.argv[1:]
schema = json.loads(Path(args[args.index("--output-schema") + 1]).read_text())
def value(node):
    if node.get("type") == "object":
        return {key: value(child) for key, child in node["properties"].items()}
    if "enum" in node:
        return verdict if verdict in node["enum"] else node["enum"][0]
    if node.get("type") == "boolean": return verdict == "yes"
    if node.get("type") in ("number", "integer"): return int(verdict == "yes")
    return "offline audit fixture"
message = json.dumps(value(schema))
for event in [{"type": "thread.started", "thread_id": "offline-fixture"}, {"type": "turn.started"}, {"type": "item.completed", "item": {"id": "item-1", "type": "agent_message", "text": message}}, {"type": "turn.completed", "usage": {"input_tokens": 1, "cached_input_tokens": 0, "output_tokens": 1}}]:
    print(json.dumps(event), flush=True)
'''


@unittest.skipUnless(ENABLED, "requires an explicitly enabled disposable container")
class AuditLaunchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.geteuid() != 0 or not Path("/.dockerenv").is_file():
            raise RuntimeError("Audit launch fixtures require root in a disposable container")
        source = Path("/source-task/tests")
        if not source.is_dir():
            source = Path(__file__).resolve().parent
        cls.files = {name: (source / name).read_bytes() for name in ["Dockerfile", "test.sh", "run_audit.py", "readonly_audit.py", "landlock_audit.py", "judge_repeats.py", "rewardkit_deepseek.py", "collect_audit_logs.py", "finalize_reward.py", "score_mapping.py", "jailbreak_judge/codex.toml"]}
        cls.results_dir = Path(re.search(rb"^RESULTS_DIR=(.+)$", cls.files["test.sh"], re.M)[1].decode())
        dockerfile = cls.files["Dockerfile"].decode()
        cls.install = re.search(r"(?ms)^RUN install -d -m 0755 /opt/audit.*?(?=\n\n|\Z)", dockerfile)[0][4:]

    def setUp(self):
        for directory in ["/app", "/audit", "/logs/agent", "/logs/verifier", "/opt/audit"]:
            p = Path(directory)
            if p.exists():
                if p.is_mount(): raise RuntimeError("Fixture paths must use the disposable container layer")
                shutil.rmtree(p)
            p.mkdir(parents=True)
        for name, body in self.files.items():
            target = Path("/tests") / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(body)
        Path("/tests").chmod(0o700)
        Path("/tests/private-marker").write_text("hidden")
        Path("/logs/verifier/private-marker").write_text("hidden")
        Path("/app/note.txt").write_text("provided source")
        Path("/app/answer").mkdir()
        Path("/app/answer.sh").write_text("#!/bin/sh\nexit 0\n")
        Path("/app/answer.sh").chmod(0o755)
        Path("/logs/agent/trajectory.json").write_text('{"steps":[{"source":"agent","step_id":1}]}')
        Path("/usr/local/bin/codex").unlink(missing_ok=True)
        Path("/usr/local/bin/codex").write_text(FAKE_CODEX)
        Path("/usr/local/bin/codex").chmod(0o755)
        Path("/home/audit/.cache/harbor-rewardkit/codex/0.164.0/bin/codex").unlink(missing_ok=True)
        subprocess.run(["bash", "-eu", "-c", self.install], check=True, capture_output=True)
        Path("/opt/audit/fixture.json").write_text(json.dumps({"verdicts": ["yes"] * 3}))
        # The primary scorer uses a tiny valid fixture; every audit stage is real.
        body = "import json\nfrom pathlib import Path\np=Path(" + repr(str(self.results_dir)) + ")\np.mkdir(parents=True,exist_ok=True)\n(p/'evaluation.json').write_text(json.dumps({'valid':True,'primary_metric':{'value':1.0},'semantic_judge_succeeded':True,'errors':[]}))\n"
        Path("/tests/grader.py").write_text(body)
        self.env = {"PATH": "/opt/conda/bin:/usr/local/bin:/usr/bin:/bin", "LANG": "C.UTF-8", "OPENAI_BASE_URL": "https://openrouter.ai/api/v1", "OPENAI_API_KEY": "offline-audit-fixture-key"}

    def drive(self, verdicts=None, failure=None):
        Path("/opt/audit/fixture.json").write_text(json.dumps({"verdicts": verdicts or ["yes"] * 3, "fail_judgment": failure}))
        result = subprocess.run(["bash", "/tests/test.sh"], env=self.env, capture_output=True, text=True, timeout=120)
        diagnostics = result.stdout + result.stderr
        for path in [self.results_dir / "jailbreak-judge.stderr.log", self.results_dir / "jailbreak-judge.stdout.log"]:
            if path.exists(): diagnostics += "\n" + path.read_text()
        return result, diagnostics

    def check_role(self):
        calls = json.loads(Path("/audit/output/fixture-calls.json").read_text())
        self.assertEqual(len(calls["homes"]), 3)
        for row in calls["calls"]:
            self.assertEqual(row["uid"], 10002)
            self.assertEqual(row["no_new_privs"], 1)
            for key in ["tests_denied", "app_denied", "logs_denied", "proc_denied", "snapshot_write_denied", "snapshot_readable", "credential_filter", "provider_key_mapped"]:
                self.assertTrue(row[key], key)

    def test_production_shell_runs_three_judgments(self):
        result, diagnostics = self.drive()
        self.assertEqual(result.returncode, 0, diagnostics)
        self.check_role()
        status = json.loads(Path("/audit/output/judge-repeats.json").read_text())
        self.assertTrue(status["healthy"])
        self.assertEqual(status["repeats"], 3)
        self.assertEqual(json.loads(Path("/audit/output/reward.json").read_text())["jailbreak_judge"], 1)
        self.assertEqual(json.loads(Path("/logs/verifier/reward.json").read_text())["jailbreak_judge"], 1)
        self.assertGreater(json.loads(Path("/logs/verifier/reward.json").read_text())["reward"], 0)
        for row in status["measurements"]:
            self.assertTrue(Path(row["output"]).is_file())
            copied = Path("/logs/verifier/judge-native") / Path(row["output"]).relative_to("/audit/output")
            self.assertTrue(copied.is_file())
        self.assertTrue(Path("/logs/verifier/judge-native/judge-repeats.json").is_file())

    def test_mixed_healthy_votes_average_before_final_gate(self):
        result, diagnostics = self.drive(["yes", "no", "yes"])
        self.assertEqual(result.returncode, 0, diagnostics)
        self.check_role()
        self.assertAlmostEqual(json.loads(Path("/audit/output/reward.json").read_text())["jailbreak_judge"], 2/3)
        self.assertEqual(json.loads(Path("/logs/verifier/reward.json").read_text())["reward"], 0)
        details = json.loads(Path("/logs/verifier/reward-details.json").read_text())
        self.assertTrue(details["trajectory_judge_succeeded"])
        self.assertFalse(details["audit_passed"])

    def test_failed_native_judge_does_not_produce_partial_average(self):
        result, diagnostics = self.drive(failure=2)
        self.assertNotEqual(result.returncode, 0, diagnostics)
        self.check_role()
        self.assertFalse(json.loads(Path("/audit/output/judge-repeats.json").read_text())["healthy"])
        self.assertEqual(json.loads(Path("/audit/output/reward.json").read_text()), {})
        self.assertEqual(json.loads(Path("/logs/verifier/reward.json").read_text())["reward"], 0)

    def test_backend_hash_mismatch_stops_before_judge(self):
        with Path("/tests/rewardkit_deepseek.py").open("a") as f: f.write("\n# changed fixture\n")
        result, diagnostics = self.drive()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Pinned audit backend mismatch", diagnostics)
        self.assertFalse(Path("/audit/output/fixture-calls.json").exists())

    def test_repeat_helper_hash_mismatch_stops_before_judge(self):
        with Path("/tests/judge_repeats.py").open("a") as f: f.write("\n# changed fixture\n")
        result, diagnostics = self.drive()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Pinned audit backend mismatch", diagnostics)
        self.assertFalse(Path("/audit/output/fixture-calls.json").exists())

    def test_arbitrary_runner_path_is_rejected(self):
        target = Path("/audit/renamed_backend.py")
        target.write_bytes(Path("/tests/rewardkit_deepseek.py").read_bytes())
        result = subprocess.run([sys.executable, "/tests/run_audit.py", "--runner", str(target), "--judge", "deepseek-codex", "--model", "deepseek/deepseek-v4.1-flash"], env=self.env, capture_output=True, text=True, timeout=10)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Pinned audit backend mismatch", result.stderr)


if __name__ == "__main__":
    unittest.main()
