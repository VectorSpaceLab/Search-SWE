"""Synthetic coding, phase probes and independent scoring; never uses the internet."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import socket
import subprocess
import sys

from receiver import request

STEPS = ['inherited', 'override', 'offline', 'shared']
AGENT_HOSTS = [['task-alpha.example'], ['step-alpha.example'], [], ['task-alpha.example']]
VERIFIER_HOSTS = [['judge-alpha.example'], ['score-alpha.example'], [], ['shared-alpha.example']]
HOSTS = ['base-alpha.example', 'vbase-alpha.example', 'task-alpha.example', 'step-alpha.example',
         'judge-alpha.example', 'score-alpha.example', 'shared-alpha.example',
         'model-left.example', 'model-right.example', 'never.example']

def run(mode, index):
    actor = os.environ['SCENARIO_ACTOR']
    step = STEPS[index]
    phase = mode + '-' + step
    if mode == 'setup':
        allowed = ['base-alpha.example']
    elif mode == 'agent':
        allowed = AGENT_HOSTS[index] + ['model-' + actor + '.example']
    else:
        allowed = VERIFIER_HOSTS[index]
    with ThreadPoolExecutor(max_workers=8) as pool:
        attempts = list(pool.map(lambda host: request(host, actor, phase, timeout=2), HOSTS))
    assert all(row['ok'] == (row['host'] in allowed) for row in attempts), 'phase network mismatch'
    app = Path('/app')
    state_file = app / 'state.json'
    report = {'actor': actor, 'phase': phase, 'allowed': allowed, 'attempts': attempts,
              'hostname': socket.gethostname()}
    if mode == 'agent':
        if index:
            state = json.loads(state_file.read_text())
            assert state['actor'] == actor and state['steps'] == STEPS[:index], 'step state crossed trials'
        else:
            assert not state_file.exists(), 'new trial inherited another trial state'
            state = {'actor': actor, 'steps': [], 'agent_hostname': socket.gethostname()}
        # A real file is authored, executed, collected and transferred by Harbor.
        (app / 'answer.py').write_text('def answer(values):\n    return sum(values) + ' + str(index) + '\n')
        subprocess.run([sys.executable, '-c', 'from answer import answer; assert answer([1,2,3]) == ' + str(6+index)],
                       cwd=app, check=True)
        state['steps'].append(step);state_file.write_text(json.dumps(state))
    elif mode == 'verifier':
        state = json.loads(state_file.read_text())
        assert state['actor'] == actor and state['steps'] == STEPS[:index+1], 'wrong transferred artifact'
        assert (state['agent_hostname'] == socket.gethostname()) == (step == 'shared'), 'wrong verifier isolation'
        subprocess.run([sys.executable, '-c', 'from answer import answer; assert answer([4,5,6]) == ' + str(15+index)],
                       cwd=app, check=True)
        report['artifact_scored'] = True
        Path('/logs/verifier/reward.txt').write_text('1.0\n')
    dest = Path('/logs/verifier/probe.json') if mode == 'verifier' else app / (phase + '.json')
    dest.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'actor': actor, 'phase': phase, 'passed': True}))

if __name__ == '__main__':
    run(sys.argv[1], int(sys.argv[2]))
