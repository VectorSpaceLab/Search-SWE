from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


MODULE_PATH = Path(__file__).with_name("run_submission.py")
SPEC = importlib.util.spec_from_file_location("agentic_search_runner", MODULE_PATH)
assert SPEC and SPEC.loader
RUNNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNNER)


class RunnerTests(unittest.TestCase):
    @unittest.skipUnless(os.geteuid() == 0, "requires the real untrusted UID boundary")
    def test_query_io_works_with_private_verifier_logs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            root.chmod(0o755)
            submission = root / "submission"
            submission.mkdir()
            private = root / "private-verifier"
            private.mkdir(mode=0o700)
            results = private / "results"
            (private / "secret").write_text("verifier-only")
            (submission / "build.sh").write_text("#!/bin/sh\nexit 0\n")
            program = (
                "import argparse,json,pathlib\n"
                "p=argparse.ArgumentParser()\n"
                "p.add_argument('--index-dir');p.add_argument('--queries');p.add_argument('--output')\n"
                "a=p.parse_args()\n"
                f"secret=pathlib.Path({str(private / 'secret')!r})\n"
                "try: secret.read_text()\n"
                "except PermissionError: pass\n"
                "else: raise SystemExit('private verifier data was exposed')\n"
                "q=json.loads(pathlib.Path(a.queries).read_text())\n"
                "pathlib.Path(a.output).write_text(json.dumps({'query_id':q['query_id'],'doc_ids':['a','b','c','d','e']})+'\\n')\n"
            )
            (submission / "run.sh").write_text(f"#!{sys.executable}\n" + program)
            for name in ("build.sh", "run.sh"):
                (submission / name).chmod(0o755)
            queries = root / "queries.jsonl"
            queries.write_text('{"query_id":"q1","question":"fixture"}\n')
            argv = ["run_submission.py", "--submission-dir", str(submission),
                    "--corpus", str(root / "corpus.jsonl"), "--queries", str(queries),
                    "--qrels", str(root / "qrels.txt"), "--results-dir", str(results),
                    "--evaluator", str(root / "evaluate.py")]

            def score(command, **kwargs):
                self.assertEqual(json.loads((results / "results.jsonl").read_text())["query_id"], "q1")
                Path(command[command.index("--report") + 1]).write_text('{"valid":true}')
                return subprocess.CompletedProcess(command, 0)

            with patch.object(sys, "argv", argv), patch.object(RUNNER.subprocess, "run", side_effect=score):
                status = RUNNER.main()
                diagnostic = (results / "evaluation.json").read_text()
                if (results / "run.stderr.log").exists():
                    diagnostic += (results / "run.stderr.log").read_text()
                self.assertEqual(status, 0, diagnostic)
            self.assertEqual(private.stat().st_mode & 0o777, 0o700)
            self.assertTrue((results / "query_inputs/query-001.jsonl").is_file())
            self.assertTrue((results / "query_outputs/query-001.jsonl").is_file())

    def test_submission_environment_preserves_only_allowed_api_keys(self) -> None:
        values = {
            "API_KEY": "private-secret",
            "MODEL_API": "https://private.invalid/v1",
            "MODEL_NAME": "private-model",
            "OTHER_API_KEY": "other-secret",
            "OPENAI_API_KEY": "agent-secret",
            "OPENAI_BASE_URL": "https://judge.invalid/v1",
            "VERIFIER_OPENAI_API_KEY": "judge-secret",
            "VERIFIER_OPENAI_BASE_URL": "https://judge.invalid/v1",
            "AGENT_OPENAI_API_KEY": "coding-agent-secret",
            "ANSWER_JUDGE_API_KEY": "answer-judge-secret",
            "SILICONFLOW_API_KEY": "removed-provider-key",
            "SILICONFLOW_API_BASE_URL": "https://removed-provider.invalid/v1",
            "OPENROUTER_API_KEY": "allowed-openrouter-key",
            "JINA_API_KEY": "allowed-jina-key",
            "PYTHONUNBUFFERED": "1",
            "UNDECLARED_VALUE": "removed",
            "REACT_MODEL": "qwen/qwen3.5-9b",
        }
        with patch.dict(os.environ, values, clear=True):
            env = RUNNER.submission_env()
        self.assertEqual(env["PYTHONUNBUFFERED"], "1")
        self.assertEqual(env["REACT_MODEL"], "qwen/qwen3.5-9b")
        for key in (
            "API_KEY",
            "MODEL_API",
            "MODEL_NAME",
            "OTHER_API_KEY",
            "OPENAI_API_KEY",
            "OPENAI_BASE_URL",
            "VERIFIER_OPENAI_API_KEY",
            "VERIFIER_OPENAI_BASE_URL",
            "AGENT_OPENAI_API_KEY",
            "ANSWER_JUDGE_API_KEY",
            "UNDECLARED_VALUE",
            "SILICONFLOW_API_KEY",
            "SILICONFLOW_API_BASE_URL",
        ):
            self.assertNotIn(key, env)
        self.assertEqual(env["OPENROUTER_API_KEY"], "allowed-openrouter-key")
        self.assertEqual(env["JINA_API_KEY"], "allowed-jina-key")


if __name__ == "__main__":
    unittest.main()
