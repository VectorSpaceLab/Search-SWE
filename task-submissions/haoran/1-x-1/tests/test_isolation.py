"""Linux container checks for the actual submitted-process access boundaries.

Run only in a disposable verifier container with TASK_ISOLATION_TEST=1.
No external service or provider credential is used.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness import invoke, seal, RUNTIME
from llm_gateway import Gateway
from prepare_judge import prepare
from judge_gateway import JudgeGateway


@unittest.skipUnless(os.environ.get('TASK_ISOLATION_TEST') == '1' and sys.platform == 'linux',
                     'requires an explicitly enabled disposable Linux verifier container')
class IsolationTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix='task-permissions-', dir='/run'))
        self.root.chmod(0o755)
        self.art = self.root / 'app'
        self.art.mkdir()
        (self.art / 'memory.json').write_text('["Use a headset."]')
        self.index = self.root / 'index'
        self.index.mkdir()
        (self.index / 'notes.json').write_text('["Use a headset."]')
        self.private = self.root / 'private'
        self.private.mkdir(mode=0o700)
        (self.private / 'labels.json').write_text('hidden labels')
        (self.private / 'reward.json').write_text('0')
        self.log = self.root / 'logs'
        self.log.mkdir(mode=0o700)

    def tearDown(self):
        shutil.rmtree(self.root)

    def script(self, name, code):
        p = self.art / name
        p.write_text('#!/bin/sh\nexec /opt/conda/bin/python -I - "$@" <<\'SCRIPT\'\n' + code + '\nSCRIPT\n')
        p.chmod(0o755)
        return p

    def probe(self, allowed, forbidden, immutable):
        return '''import json, os, socket
from pathlib import Path
assert os.geteuid() == 10001
for key in ("OPENROUTER_API_KEY", "ANSWER_API_KEY", "ANSWER_API_BASE_URL", "ANSWER_MODEL", "ANSWER_JUDGE_API_KEY", "OPENAI_API_KEY"):
    assert key not in os.environ, key
for path in ALLOWED:
    Path(path).read_bytes()
for path in FORBIDDEN:
    try: Path(path).read_bytes()
    except OSError: pass
    else: raise AssertionError("unexpected read: " + path)
for path in IMMUTABLE:
    try: Path(path).write_text("tampered")
    except OSError: pass
    else: raise AssertionError("unexpected write: " + path)
try: socket.socket()
except OSError: pass
else: raise AssertionError("network socket allowed")
Path("scratch").write_text("writable")
with open("/dev/null", "w") as sink: sink.write("discarded")
'''.replace('ALLOWED', repr(list(map(str, allowed)))).replace('FORBIDDEN', repr(list(map(str, forbidden)))).replace('IMMUTABLE', repr(list(map(str, immutable))))

    def test_builder_search_answer_have_distinct_views(self):
        for name in ('build_index.sh', 'search.sh', 'answer.sh'):
            self.script(name, 'pass')
        common_denied = [self.private / 'labels.json', self.private / 'reward.json', '/proc/1/environ']
        cases = [
            ('build_index.sh', [self.art / 'memory.json'], [self.index / 'notes.json', self.art / 'search.sh', self.art / 'answer.sh']),
            ('search.sh', [self.index / 'notes.json'], [self.art / 'memory.json', self.art / 'build_index.sh', self.art / 'answer.sh']),
            ('answer.sh', [], [self.art / 'memory.json', self.index / 'notes.json', self.art / 'search.sh', self.art / 'build_index.sh']),
        ]
        for stage, allowed, denied in cases:
            script = self.script(stage, self.probe(allowed, common_denied + denied,
                                                   [*allowed, self.private / 'reward.json', self.art / stage]))
            seal(self.art)
            seal(self.index, executable=False)
            read = [script] + ([self.index] if stage == 'search.sh' else allowed)
            invoke([script], read, self.root / stage.replace('.sh', ''), self.log, stage, 15)
        self.assertEqual((self.private / 'reward.json').read_text(), '0')

    def test_answer_api_transport_has_no_provider_key(self):
        inputs = self.root / 'input'
        inputs.mkdir(mode=0o755)
        client = inputs / 'llm_client.py'
        shutil.copyfile(Path(__file__).with_name('llm_client.py'), client)
        script = self.script('answer.sh', self.probe([client], [self.art / 'memory.json'], [client]) + '''
import importlib.util
s=importlib.util.spec_from_file_location("client", os.environ["TASK_LLM_CLIENT"])
m=importlib.util.module_from_spec(s); s.loader.exec_module(m)
r=m.chat_completion(messages=[{"role":"user", "content":"A question"}], model="qwen/qwen3.5-9b")
assert r["choices"][0]["message"]["content"] == "A response"
''')
        seal(self.art)
        with Gateway('test-provider-key', 2, self.log / 'api.json') as gateway:
            gateway.client_path = client
            with patch.object(gateway, 'forward', return_value={'choices':[{'message':{'content':'A response'}}]}):
                invoke([script], [script, inputs], self.root / 'answer', self.log, 'answer', 15, gateway)
        self.assertEqual(json.loads((self.log / 'api.json').read_text())['calls'], 1)

    def test_real_builder_search_and_answer_pipeline(self):
        import harness
        self.script('build_index.sh', """
import argparse, json
from pathlib import Path
p=argparse.ArgumentParser(); p.add_argument('--memory'); p.add_argument('--output'); a=p.parse_args()
notes=json.loads(Path(a.memory).read_text())
Path(a.output).mkdir(); Path(a.output, 'notes.json').write_text(json.dumps(notes))
""")
        self.script('search.sh', """
import argparse, json
from pathlib import Path
p=argparse.ArgumentParser(); p.add_argument('--index'); p.add_argument('--question'); p.add_argument('--output'); a=p.parse_args()
Path(a.output).write_text(Path(a.index, 'notes.json').read_text())
""")
        self.script('answer.sh', """
import argparse, json
from pathlib import Path
p=argparse.ArgumentParser(); p.add_argument('--question'); p.add_argument('--memories'); p.add_argument('--output'); a=p.parse_args()
Path(a.output).write_text(json.loads(Path(a.memories).read_text())[0])
""")
        history = self.root / 'history.jsonl'
        history.write_text(json.dumps({'text':'source dialogue ' * 200}) + '\n')
        for name, row in (
            ('queries', {'query_id':'q', 'question':'Which equipment? \"quoted\" $(literal)'}),
            ('golden_answers', {'query_id':'q', 'answer':'Use a headset.', 'criteria':['headset']}),
            ('evidence', {'query_id':'q', 'evidence':[{'text':'Use a headset.'}]}),
        ):
            (self.root / (name + '.jsonl')).write_text(json.dumps(row) + '\n')
        with patch.dict(os.environ, {'OPENROUTER_API_KEY':'test-key'}), \
             patch('harness.llm', side_effect=lambda system, payload: ({'citations':[{'memory_index':0,'quote':'Use a headset.'}]} if 'retrieved_texts' in payload else {'hit':True,'matches':[{'passage_index':0,'reference_fact':'Use a headset.'}]} if 'retrieved_passages' in payload else {'supported':True} if 'claims' in payload else {'correct':True}, {})):
            result = harness.evaluate(self.art, history, self.root / 'queries.jsonl',
                                      self.root / 'golden_answers.jsonl', self.log)
        self.assertTrue(result['valid'], result)
        self.assertEqual(json.loads((self.log / 'retrievals.json').read_text()), {'q':['Use a headset.']})
        self.assertEqual(json.loads((self.log / 'submitted_answers.json').read_text())['q']['answer'], 'Use a headset.')

    def test_judge_environment_and_kernel_boundary(self):
        trajectory = self.root / 'trajectory.json'
        trajectory.write_text('{}')
        judge = self.root / 'audit'
        judge.mkdir()
        with JudgeGateway('https://unused.example', 'real-provider-key', 'test-model') as gateway:
            env = prepare(judge, gateway, trajectory)
            self.assertNotIn('real-provider-key', json.dumps(env))
            self.assertNotIn('OPENROUTER_API_KEY', env)
            self.assertNotIn('ANSWER_API_KEY', env)
            self.assertNotIn('ANSWER_JUDGE_API_KEY', env)
            # Exercise the exact judge_fs policy, replacing only the final exec with a probe.
            script = self.script('answer.sh', 'pass')
            seal(self.art)
            source = Path(__file__).with_name('judge_fs.py').read_text()
            source = source.replace('"/app"', repr(str(self.art)))
            source = source.replace('os.execv("/usr/local/bin/codex", ["/usr/local/bin/codex", *sys.argv[1:]])', 'probe()')
            probe = '''
def probe():
    assert os.geteuid() == 10002
    Path(ALLOWED).read_bytes()
    for path in DENIED:
        try: Path(path).read_bytes()
        except OSError: pass
        else: raise AssertionError("judge read: " + path)
    for path in WRITES:
        try: Path(path).write_text("tampered")
        except OSError: pass
        else: raise AssertionError("judge write: " + path)
    import subprocess
    try: subprocess.run([SUBMITTED], check=True)
    except PermissionError: pass
    else: raise AssertionError("direct submitted executable allowed")
    Path(os.environ["TMPDIR"], "scratch").write_text("ok")
'''.replace('ALLOWED', repr(str(trajectory))).replace('DENIED', repr([str(self.private / 'labels.json'), '/proc/self/environ', str(self.log / 'final.json')])).replace('WRITES', repr([str(self.art / 'memory.json'), str(self.private / 'reward.json'), str(judge / 'out/score.json')])).replace('SUBMITTED', repr(str(script)))
            # Only the copied input is accessible to the judge.
            probe = probe.replace(repr(str(trajectory)), repr(str(judge / 'input/trajectory.json')))
            source = source.replace('if __name__ == "__main__":', probe + '\nif __name__ == "__main__":')
            helper = judge / 'helpers/probe.py'
            helper.write_text(source)
            os.chown(helper, 0, 10002); helper.chmod(0o640)
            result = subprocess.run(['/opt/conda/bin/python','-I',str(helper)], env=env,
                                    user=10002, group=10002, extra_groups=[10001],
                                    cwd=judge / 'work', capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
