import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("paper_query_runner", Path(__file__).with_name("run_queries.py"))
RUNNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNNER)


class QueryRunnerTests(unittest.TestCase):
    def test_five_workers_25_queries_independent_deadlines_and_order(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'inputs').mkdir()
            (root / 'outputs').mkdir()
            args = argparse.Namespace(queries=root / "inputs/queries.jsonl", index_dir=root,
                                      output=root / "outputs/output.jsonl", logs_dir=root,
                                      run_script=root / "run.sh", timeout=900)
            barrier = threading.Barrier(5)
            lock = threading.Lock()
            state = {"active": 0, "peak": 0, "timeouts": []}

            class Process:
                def __init__(self, command, **kwargs):
                    self.query_id = json.loads(Path(command[command.index('--queries') + 1]).read_text())["query_id"]
                    self.output = Path(command[command.index('--output') + 1])
                    self.test_env = kwargs['env']
                    with lock:
                        state['active'] += 1
                        state['peak'] = max(state['peak'], state['active'])
                def wait(self, timeout):
                    if int(self.query_id[1:]) < 5:
                        barrier.wait(5)
                    with lock:
                        state['timeouts'].append(timeout)
                        state['active'] -= 1
                    if self.query_id == 'q7':
                        raise subprocess.TimeoutExpired('run.sh', timeout)
                    self.output.write_text(json.dumps({'query_id': self.query_id, 'answer': 'ok', 'evidence': 'doc'}) + '\n')
                    return 0

            with patch.object(RUNNER.os, 'chown'), patch.object(RUNNER, 'stop_group'), \
                    patch.object(RUNNER.subprocess, 'Popen', Process):
                with RUNNER.ThreadPoolExecutor(max_workers=5) as pool:
                    futures = [pool.submit(RUNNER.run_query, i, {'query_id': f'q{i}'}, args) for i in range(25)]
                    results = [f.result() for f in futures]
            self.assertEqual(state['peak'], 5)
            self.assertEqual(state['timeouts'], [900] * 25)
            self.assertEqual([timing['query_id'] for _, timing in results], [f'q{i}' for i in range(25)])
            self.assertEqual(sum(record is not None for record, _ in results), 24)
            self.assertIn('900 seconds', results[7][1]['error'])

    def test_both_judge_keys_are_private(self):
        with patch.dict(RUNNER.os.environ, {'ANSWER_JUDGE_API_KEY': 'private-answer',
                                         'OPENAI_API_KEY': 'private-trajectory',
                                         'OPENROUTER_API_KEY': 'allowed'}, clear=True):
            env = RUNNER.submission_env()
        self.assertNotIn('ANSWER_JUDGE_API_KEY', env)
        self.assertNotIn('OPENAI_API_KEY', env)
        self.assertEqual(env['OPENROUTER_API_KEY'], 'allowed')


if __name__ == '__main__':
    unittest.main()
