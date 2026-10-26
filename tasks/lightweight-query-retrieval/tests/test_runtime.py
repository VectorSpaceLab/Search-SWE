"""CPU-only integration checks inside a disposable root verifier container.

The shell tests substitute deterministic grader/judge executables and restore
them afterward. They verify orchestration, not GPU retrieval or LLM judgment.
"""
import json
import os
from pathlib import Path
import pwd
import socket
import subprocess
import tempfile
import unittest

from grader import command


IN_CONTAINER = (os.environ.get("SEARCH_SWE_RUN_CONTAINER_TESTS") == "1"
                and Path("/.dockerenv").exists() and os.geteuid() == 0)


@unittest.skipUnless(IN_CONTAINER, "requires a disposable root verifier container")
class SubmissionIsolationTests(unittest.TestCase):
    def test_java_runtime_survives_sanitized_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            scratch = Path(directory)
            os.chown(scratch, 10001, 10001)
            probe = '''
import os, subprocess
assert os.environ['JAVA_HOME'] == '/opt/java/openjdk'
assert os.environ['OPENAI_API_KEY'] == 'search-swe-offline-no-credentials'
version = subprocess.run(['java', '-version'], capture_output=True, text=True)
assert version.returncode == 0, version.stderr
from pyserini.search.lucene import LuceneSearcher
from jnius import autoclass
assert autoclass('java.lang.System').getProperty('java.home') == '/opt/java/openjdk'
print('sanitized Java, JNI and Pyserini imports succeeded')
'''
            result = subprocess.run(command(["/opt/conda/bin/python", "-c", probe], scratch),
                                    text=True, capture_output=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_network_credentials_and_trajectory_are_isolated(self):
        self.assertEqual(pwd.getpwnam("submission").pw_uid, 10001)
        Path("/logs/agent").mkdir(parents=True, exist_ok=True, mode=0o700)
        Path("/logs/agent").chmod(0o700)
        Path("/logs/agent/trajectory.json").write_text('{"steps":[{}]}')
        Path("/logs/agent/trajectory.json").chmod(0o600)
        Path("/logs/verifier/.private").mkdir(parents=True, exist_ok=True, mode=0o700)
        Path("/logs/verifier").chmod(0o700)
        Path("/logs/verifier/.private/judge-reward.json").write_text('{"jailbreak_judge":1}')
        Path("/tests").chmod(0o700)
        # Socket creation is possible for the root-side judge even with no
        # external network; child denial must come from its own seccomp policy.
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM):
            pass
        with tempfile.TemporaryDirectory() as directory:
            scratch = Path(directory)
            os.chown(scratch, 10001, 10001)
            probe = '''
import json, os, socket, subprocess, sys
from pathlib import Path
assert os.getuid() == 10001
assert 'NoNewPrivs:\\t1' in Path('/proc/self/status').read_text()
assert os.environ['OPENAI_API_KEY'] == 'search-swe-offline-no-credentials'
for key in ('OPENAI_BASE_URL','OPENROUTER_API_KEY','VERIFIER_OPENAI_API_KEY','HTTPS_PROXY'):
    assert key not in os.environ, key
for path in ('/logs/agent/trajectory.json','/logs/verifier/.private/judge-reward.json','/tests/grader.py'):
    for mode in ('r','w'):
        try:
            with open(path,mode): pass
        except PermissionError: pass
        else: raise AssertionError(path+' accessible with mode '+mode)
for family in (socket.AF_INET,socket.AF_INET6):
    try: socket.socket(family,socket.SOCK_STREAM)
    except PermissionError: pass
    else: raise AssertionError('Internet socket allowed')
a,b=socket.socketpair()
a.close();b.close()
child = subprocess.run([sys.executable,'-c','import socket; socket.socket(socket.AF_INET)'],capture_output=True)
assert child.returncode != 0 and b'PermissionError' in child.stderr
print(json.dumps({'uid':os.getuid(),'network_blocked':True,'protected':True}))
'''
            environment = {**os.environ, "OPENAI_API_KEY": "offline-test-sentinel",
                           "VERIFIER_OPENAI_API_KEY": "offline-test-sentinel",
                           "OPENROUTER_API_KEY": "offline-test-sentinel",
                           "OPENAI_BASE_URL": "https://offline.invalid",
                           "HTTPS_PROXY": "http://offline.invalid"}
            result = subprocess.run(command(["/opt/conda/bin/python", "-c", probe], scratch),
                                    env=environment, text=True, capture_output=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout),
                             {"uid": 10001, "network_blocked": True, "protected": True})


@unittest.skipUnless(IN_CONTAINER, "requires a disposable root verifier container")
class ShellGateTests(unittest.TestCase):
    def test_actual_entrypoint_with_controlled_grader_and_judge_results(self):
        tests = Path("/tests")
        originals = {name: (tests / name).read_bytes() for name in
                     ("grader.py", "rewardkit_deepseek.py", "finalize_reward.py")}
        self.addCleanup(lambda: [(tests / name).write_bytes(data) for name, data in originals.items()])
        Path("/app").mkdir(exist_ok=True)
        Path("/logs/agent").mkdir(parents=True, exist_ok=True)
        (tests / "grader.py").write_text('''
import json, os
from pathlib import Path
root=Path('/logs/verifier')
report={'task_id':'lightweight-query-retrieval','valid':True,'query_count':1271,
        'reward':float(os.environ.get('FIXTURE_RAW_REWARD','0.375'))}
(root/'report.json').write_text(json.dumps(report))
assert float((root/'reward.txt').read_text()) == 0
assert json.loads((root/'reward.json').read_text())['reward'] == 0
raise SystemExit(int(os.environ.get('FIXTURE_GRADER_EXIT','0')))
''')
        (tests / "rewardkit_deepseek.py").write_text('''
import json, os, sys
from pathlib import Path
root=Path('/logs/verifier')
assert json.loads((root/'reward.json').read_text())['reward'] == 0
assert float((root/'reward.txt').read_text()) == 0
assert sys.argv[sys.argv.index('--judge')+1] == 'deepseek-codex'
assert sys.argv[sys.argv.index('--model')+1] == 'deepseek/deepseek-v4.1-flash'
output=Path(sys.argv[sys.argv.index('--output')+1])
assert output == root/'.private/judge-reward.json'
output.write_text(os.environ['FIXTURE_JUDGE_OUTPUT'])
assert json.loads((root/'reward.json').read_text())['reward'] == 0
raise SystemExit(int(os.environ.get('FIXTURE_JUDGE_EXIT','0')))
''')
        cases = [
            ("pass", {}, '{"jailbreak_judge":1}', 0.375, 0),
            ("reject-answer-table-decision", {}, '{"jailbreak_judge":0}', 0.0, 0),
            ("fractional", {}, '{"jailbreak_judge":0.5}', 0.0, 1),
            ("string", {}, '{"jailbreak_judge":"1"}', 0.0, 1),
            ("boolean", {}, '{"jailbreak_judge":true}', 0.0, 1),
            ("missing-result", {}, '{}', 0.0, 1),
            ("bad-json", {}, 'broken', 0.0, 1),
            ("judge-failure-after-pass", {"FIXTURE_JUDGE_EXIT": "17"}, '{"jailbreak_judge":1}', 0.0, 1),
            ("judge-timeout-status", {"FIXTURE_JUDGE_EXIT": "124"}, '{"jailbreak_judge":1}', 0.0, 1),
            ("grader-failure-after-score", {"FIXTURE_GRADER_EXIT": "17"}, '{"jailbreak_judge":1}', 0.0, 1),
            ("missing-credentials", {"OPENAI_API_KEY": ""}, '{"jailbreak_judge":1}', 0.0, 1),
            ("missing-trajectory", {}, '{"jailbreak_judge":1}', 0.0, 1),
            ("legitimate-zero", {"FIXTURE_RAW_REWARD": "0"}, '{"jailbreak_judge":1}', 0.0, 0),
            ("finalizer-crash-after-write", {}, '{"jailbreak_judge":1}', 0.0, 1),
        ]
        for name, changes, decision, expected, exit_code in cases:
            with self.subTest(case=name):
                trajectory = Path("/logs/agent/trajectory.json")
                trajectory.write_text('{"steps":[{"source":"agent","message":"synthetic flow fixture"}]}')
                if name == "missing-trajectory":
                    trajectory.unlink()
                private = Path("/logs/verifier/.private")
                private.mkdir(parents=True, exist_ok=True)
                (private / "judge-reward.json").write_text('{"jailbreak_judge":1}')
                if name == "finalizer-crash-after-write":
                    (tests / "finalize_reward.py").write_text("from pathlib import Path\nPath('/logs/verifier/reward.txt').write_text('1')\nraise SystemExit(23)\n")
                else:
                    (tests / "finalize_reward.py").write_bytes(originals["finalize_reward.py"])
                env = {**os.environ, "OPENAI_BASE_URL": "https://openrouter.ai/api/v1",
                       "OPENAI_API_KEY": "offline-test-sentinel", "FIXTURE_JUDGE_OUTPUT": decision,
                       **changes}
                result = subprocess.run(["bash", "/tests/test.sh"], env=env,
                                        text=True, capture_output=True, timeout=30)
                self.assertEqual(result.returncode, exit_code, result.stderr)
                self.assertEqual(float(Path("/logs/verifier/reward.txt").read_text()), expected)
                self.assertEqual(json.loads(Path("/logs/verifier/reward.json").read_text())["reward"], expected)


if __name__ == "__main__":
    unittest.main()
