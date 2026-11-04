"""Offline child-process regression tests; no provider calls are made."""

import sys
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(TASK_ROOT / "tests"))


import ctypes.util
import errno
import importlib.util
import os
import socket
import subprocess
import tempfile
import time
import unittest

HELPER = (TASK_ROOT / "tests" / "offline_exec.py")


def clean_env():
    return {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "LANG": "C.UTF-8",
        "PYTHONDONTWRITEBYTECODE": "1",
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
    }


@unittest.skipUnless(sys.platform == "linux" and ctypes.util.find_library("seccomp"),
                     "Linux and libseccomp are required")
class OfflineExecTests(unittest.TestCase):
    def execute(self, code, *, restricted=True, **kwargs):
        argv = [sys.executable, "-I"]
        if restricted:
            argv += [str(HELPER), sys.executable, "-I"]
        return subprocess.run(
            argv + ["-c", code], env=clean_env(),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, timeout=15, **kwargs,
        )

    def test_unrestricted_control_can_create_network_socket(self):
        result = self.execute(
            "import socket; socket.socket(socket.AF_INET, socket.SOCK_STREAM).close()",
            restricted=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_ipv4_ipv6_tcp_and_udp_are_blocked(self):
        for family in (socket.AF_INET, socket.AF_INET6):
            for kind in (socket.SOCK_STREAM, socket.SOCK_DGRAM):
                code = (
                    "import socket, errno\n"
                    "try:\n"
                    f" socket.socket({int(family)}, {int(kind)})\n"
                    "except OSError as error:\n"
                    " assert error.errno == errno.EPERM, error\n"
                    "else:\n"
                    " raise AssertionError('network socket was allowed')\n"
                )
                with self.subTest(family=family, kind=kind):
                    result = self.execute(code)
                    self.assertEqual(result.returncode, 0, result.stderr)

    def test_local_unix_ipc_remains_available(self):
        result = self.execute(
            "import socket; a,b=socket.socketpair(); "
            "a.sendall(b'ok'); assert b.recv(2)==b'ok'; a.close(); b.close()"
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_inherited_network_descriptor_is_closed(self):
        with socket.socket() as network:
            code = (
                "import os, stat\n"
                "try:\n"
                f" value=os.fstat({network.fileno()}).st_mode\n"
                "except OSError:\n"
                " pass\n"
                "else:\n"
                " assert not stat.S_ISSOCK(value), 'inherited network socket'\n"
            )
            result = self.execute(code, pass_fds=(network.fileno(),))
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_network_socket_on_stdin_is_replaced(self):
        with socket.socket() as network:
            result = self.execute("import os; assert os.read(0,1)==b''", stdin=network)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_restriction_survives_child_exec(self):
        result = self.execute(
            "import subprocess, sys; result=subprocess.run([sys.executable,'-I','-c',"
            "'import socket; socket.socket()'],capture_output=True,text=True); "
            "assert result.returncode != 0; assert 'Operation not permitted' in result.stderr"
        )
        self.assertEqual(result.returncode, 0, result.stderr)


@unittest.skipUnless(
    os.environ.get("SEARCH_SWE_RUN_ISOLATION_TESTS") == "1"
    and hasattr(os, "geteuid") and os.geteuid() == 0
    and Path("/.dockerenv").is_file(),
    "explicit disposable root container required",
)
class GraderBoundaryTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location(
            "offline_grader_under_test", (TASK_ROOT / "tests" / "grader.py")
        )
        self.grader = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.grader)
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.root.chmod(0o711)
        self.grader.LOG = self.root
        Path("/app").mkdir(exist_ok=True)
        Path("/app").chmod(0o755)

    def tearDown(self):
        if hasattr(self.grader, "stop"):
            self.grader.stop()
        else:
            self.grader.kill_user("submission")
        self.temp.cleanup()

    def invoke(self, code, label, timeout=15):
        argv = [sys.executable, "-I", "-c", code]
        if hasattr(self.grader, "run"):
            return self.grader.run(argv, label, timeout)
        work = self.root / (label + "-work")
        self.grader.stage_directory(work, "submission")
        return self.grader.run_stage(
            "submission", argv, work, self.root / label, timeout,
        )

    def test_real_grader_launch_blocks_network(self):
        error_type = getattr(self.grader, "SubmissionError", ValueError)
        with self.assertRaises(error_type):
            self.invoke("import socket; socket.socket()", "network")
        self.assertIn(
            "Operation not permitted",
            (self.root / "network.stderr.log").read_text(),
        )

    def test_real_grader_launch_is_unprivileged_and_filters_judge_key(self):
        old = os.environ.get("OPENAI_API_KEY")
        os.environ["OPENAI_API_KEY"] = "verifier-only-fixture"
        try:
            self.invoke(
                "import os; assert os.getuid()==10001; "
                "assert 'OPENAI_API_KEY' not in os.environ; "
                "import socket; a,b=socket.socketpair(); "
                "a.sendall(b'ok'); assert b.recv(2)==b'ok'",
                "local",
            )
        finally:
            if old is None:
                os.environ.pop("OPENAI_API_KEY", None)
            else:
                os.environ["OPENAI_API_KEY"] = old

    def test_real_grader_timeout_terminates_submission(self):
        error_type = getattr(self.grader, "SubmissionError", ValueError)
        with self.assertRaises(error_type):
            self.invoke("import time; time.sleep(30)", "timeout", timeout=0.2)
        # Signal delivery and orphan reaping are asynchronous. Zombies cannot
        # execute or retain a usable network connection.
        live = []
        for _ in range(100):
            result = subprocess.run(
                ["ps", "-u", "submission", "-o", "stat="],
                capture_output=True, text=True,
            )
            live = [state for state in result.stdout.split() if not state.startswith("Z")]
            if not live:
                break
            time.sleep(0.02)
        self.assertEqual(live, [])


if __name__ == "__main__":
    unittest.main()
