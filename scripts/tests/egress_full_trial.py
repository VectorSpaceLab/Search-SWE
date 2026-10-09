"""Full Harbor Trial.run gate: two simultaneous trials of one four-step task.

Formal adapter/Oracle extension points only. No patched Harbor methods, API calls,
task-1-1 edits, proxy forwarding, or changes to the operator Docker daemon.
"""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.modules['scripts.tests.egress_full_trial'] = sys.modules[__name__]

from harbor.models.trial.config import TrialConfig
from harbor.models.task.config import TaskConfig
from harbor.trial.trial import Trial
from scripts.harbor_environments import PhaseScopedDocker
from scripts.tests.egress_scenarios_fixture import DirectReceiver, Receiver

INSTANCES = []
BARRIERS = {}

class ObservedDocker(PhaseScopedDocker):
    def __init__(self, *args, **kwargs):
        self.observation = {'session': kwargs['session_id'], 'policies': []}
        super().__init__(*args, **kwargs)
        self.observation['instance'] = self._instance
        INSTANCES.append(self)

    async def _apply_network_policy(self, policy):
        start = time.monotonic_ns()
        await super()._apply_network_policy(policy)
        self.observation['policies'].append({'start_ns': start, 'ack_ns': time.monotonic_ns(),
                                            'policy': policy.model_dump(mode='json')})

    async def start(self, force_build):
        await super().start(force_build)
        container = await self._run_docker_compose_command(['ps', '-q', 'harbor-docker-egress-control-sidecar'])
        info = json.loads(await asyncio.to_thread(docker, 'inspect', container.stdout.strip()))[0]
        addresses = [v['IPAddress'] for v in info['NetworkSettings']['Networks'].values()]
        assert len(addresses) == 1 and addresses[0]
        self.observation.update(started_ns=time.monotonic_ns(), source=addresses[0], private=self._private.name)
        # Both real separate-verifier environments must coexist at every step.
        if '__verifier__' in self.observation['session']:
            step = self.observation['session'].split('__verifier__')[-1]
            await asyncio.wait_for(BARRIERS.setdefault(step, asyncio.Barrier(2)).wait(), timeout=90)

    async def stop(self, delete):
        await super().stop(delete)
        self.observation.setdefault('stopped_ns', time.monotonic_ns())

def docker(*args):
    return subprocess.run(['docker', *args], capture_output=True, text=True, check=True, timeout=90).stdout

def allow(*hosts):
    return {"network_mode": "allowlist", "allowed_hosts": list(hosts)}


def task_config(name, image):
    return TaskConfig.model_validate({
        "environment": {"docker_image": image, **allow(f"base-{name}.example")},
        "agent": allow(f"task-{name}.example"),
        "verifier": {**allow(f"judge-{name}.example"),
                     "environment": {"docker_image": image, **allow(f"vbase-{name}.example")}},
        "steps": [
            {"name": "inherited"},
            {"name": "override", "agent": allow(f"step-{name}.example"),
             "verifier": {**allow(f"score-{name}.example"),
                          "environment": {"docker_image": image, "network_mode": "no-network"}}},
            {"name": "offline", "agent": {"network_mode": "no-network"},
             "verifier": {"network_mode": "no-network"}},
            {"name": "shared", "verifier": {"environment_mode": "shared", **allow(f"shared-{name}.example")}},
        ]})


def create_task(output, image):
    directory = output / 'task'
    directory.mkdir()
    (directory / 'environment').mkdir()
    (directory / 'environment/Dockerfile').write_text('FROM ' + image + '\n')
    cfg = task_config('alpha', image).model_dump(mode='json', exclude_none=True)
    cfg['environment'].update(workdir='/app', cpus=1, memory_mb=512)
    cfg['agent']['timeout_sec'] = 60
    cfg['verifier']['timeout_sec'] = 60
    cfg['artifacts'] = ['/app']
    for index, step in enumerate(cfg['steps']):
        name = step['name']
        step['verifier']['env'] = {'FIXTURE_STEP_INDEX': str(index)}
        step['min_reward'] = 1.0
        root = directory / 'steps' / name
        for sub in ('workdir', 'solution', 'tests'):
            (root / sub).mkdir(parents=True)
        (root / 'instruction.md').write_text('Synthetic fixture: construct and independently score an arithmetic function.\n')
        (root / 'workdir/setup.sh').write_text(f'#!/bin/sh\nset -eu\npython /opt/fixture/client.py setup {index}\n')
        (root / 'solution/solve.sh').write_text(f'#!/bin/sh\nset -eu\npython /opt/fixture/client.py agent {index}\n')
        (root / 'tests/test.sh').write_text(f'#!/bin/sh\nset -eu\npython /opt/fixture/client.py verifier {index}\n')
        (root / 'tests/Dockerfile').write_text('FROM ' + image + '\n')
    (directory / 'task.toml').write_text(TaskConfig.model_validate(cfg).model_dump_toml())
    return directory

async def main(args):
    output = args.output.resolve();output.mkdir(parents=True, exist_ok=False)
    identity = 'searchswe-full-trial-' + uuid.uuid4().hex[:10]
    result = {'status': 'running', 'identity': identity, 'checks': [], 'cleanup_errors': [],
              'transport': args.transport,
              'scope': 'synthetic Oracle coding and real independent scoring; no model API calls',
              'release_ready': False}
    receiver, futures = None, []
    try:
        sources = [Path(__file__), Path(__file__).with_name('egress_full_trial_client.py'),
                   ROOT / 'scripts/tests/egress_scenarios_fixture.py',
                   ROOT / 'scripts/harbor_environments.py']
        result['sources'] = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
        # Fail before build if either required input is not already local.
        inputs = {role: json.loads(docker('image', 'inspect', name))[0]['Id']
                  for role, name in [('python', args.python_image), ('gateway', args.gateway_image)]}
        bridge = json.loads(docker('network', 'inspect', 'bridge'))[0]['IPAM']['Config'][0]['Gateway']
        receiver_type = DirectReceiver if args.transport == 'direct' else Receiver
        receiver = receiver_type((bridge, 0), output / 'receiver.jsonl')
        threading.Thread(target=receiver.serve_forever, daemon=True).start()
        image = identity + ':fixture'
        context = output / 'image';context.mkdir()
        shutil.copyfile(Path(__file__).with_name('egress_full_trial_client.py'), context / 'client.py')
        shutil.copyfile(ROOT / 'scripts/tests/egress_scenarios_fixture.py', context / 'receiver.py')
        (context / 'origin-port').write_text(str(receiver.server_address[1] if args.transport == 'direct' else 80))
        (context / 'test.sh').write_text('#!/bin/sh\nset -eu\npython /opt/fixture/client.py verifier "$FIXTURE_STEP_INDEX"\n')
        (context / 'Dockerfile').write_text('FROM ' + args.python_image + '\nRUN mkdir -p /app /tests /opt/fixture\n'
            'COPY client.py receiver.py /opt/fixture/\nCOPY origin-port /tmp/searchswe-fixture-port\n'
            'COPY test.sh /tests/test.sh\nWORKDIR /app\n')
        with (output / 'build.log').open('w') as log:
            p = await asyncio.create_subprocess_exec('docker', 'build', '--network=none', '--pull=false', '-t', image, str(context),
                                                      stdout=log, stderr=log)
            if await asyncio.wait_for(p.wait(), 90):
                raise RuntimeError('fixture image build failed')
        result['images'] = {k: json.loads(docker('image', 'inspect', v))[0]['Id']
                            for k,v in [('fixture', image), ('gateway', args.gateway_image), ('python', args.python_image)]}
        if any(result['images'][role] != image_id for role, image_id in inputs.items()):
            raise RuntimeError('fixture input image changed during build')
        task = create_task(output, image)
        result['fixture_sha256'] = {str(p.relative_to(output)): hashlib.sha256(p.read_bytes()).hexdigest()
                                   for root in (task, context) for p in root.rglob('*') if p.is_file()}
        config = output / 'egress.json'
        document = {'version': 1, 'image': args.gateway_image,
            'upstream': {'url': f'http://{bridge}:{receiver.server_address[1]}'},
            'dns': {'doh_url': 'https://resolver.example/dns-query'}}
        if args.transport == 'direct':
            document = receiver.configuration(args.gateway_image)
        config.write_text(json.dumps(document))
        environment_kwargs = ({'egress_image': args.gateway_image, 'egress_dns': document['dns']['servers'][0]}
                              if args.transport == 'direct' else {'egress_config': str(config)})
        trials = []
        for actor in ('left', 'right'):
            cfg = TrialConfig.model_validate({'task': {'path': str(task)}, 'trial_name': identity + '-' + actor,
                'trials_dir': str(output / 'trials'),
                'agent': {'name': 'oracle', 'extra_allowed_hosts': ['model-' + actor + '.example']},
                'environment': {'import_path': 'scripts.tests.egress_full_trial:ObservedDocker',
                    'kwargs': environment_kwargs, 'env': {'SCENARIO_ACTOR': actor}},
                'verifier': {'env': {'SCENARIO_ACTOR': actor}}})
            trials.append(await Trial.create(cfg))
        futures = [asyncio.create_task(t.run()) for t in trials]
        replies = await asyncio.wait_for(asyncio.gather(*futures), 900)
        for actor, reply in zip(('left','right'), replies):
            if reply.exception_info or len(reply.step_results or []) != 4:
                raise AssertionError('full Trial.run did not finish four steps')
            for step in reply.step_results:
                if step.exception_info or not step.verifier_result or step.verifier_result.rewards != {'reward': 1.0}:
                    raise AssertionError('step coding/artifact/scoring failed')
                result['checks'].append({'case': actor + '-' + step.step_name, 'passed': True, 'reward': 1.0})
            if reply.verifier_result.rewards != {'reward': 1.0}:
                raise AssertionError('trial aggregation failed')
        events = receiver.snapshot()
        for event in events:
            if event['kind'] == 'fixture_error':
                raise AssertionError('receiving fixture failed')
            if event['kind'] != ('http' if args.transport == 'direct' else 'connect'):
                continue
            t = event['received_ns']
            envs = [e.observation for e in INSTANCES if e.observation.get('source') == event['source']
                    and e.observation.get('started_ns', t+1) <= t < e.observation.get('stopped_ns', t+1)]
            if len(envs) != 1:
                raise AssertionError('receiving connection lacks unique live instance attribution')
            policies = [p for p in envs[0]['policies'] if p['ack_ns'] <= t]
            host = event['host'] if args.transport == 'direct' else event['target'].removesuffix(':80')
            if not policies or host not in policies[-1]['policy']['allowed_hosts']:
                raise AssertionError('unauthorized request arrived at receiving oracle')
        result['checks'].append({'case': 'receiving-authorizations', 'passed': True, 'events': len(events)})
        for step in ('inherited', 'override', 'offline'):
            pair = [e.observation for e in INSTANCES if e.observation['session'].endswith('__verifier__'+step)]
            if len(pair) != 2 or max(e['started_ns'] for e in pair) >= min(e['stopped_ns'] for e in pair):
                raise AssertionError('same-task separate verifiers did not overlap')
            if pair[0]['private'] == pair[1]['private'] or pair[0]['instance'] == pair[1]['instance']:
                raise AssertionError('same-task verifiers reused private state')
            result['checks'].append({'case': 'overlapping-verifiers-'+step, 'passed': True})
        result['status'] = 'passed'
    except BaseException as e:
        result.update(status='failed', error_class=type(e).__name__, error=str(e))
    finally:
        for f in futures:
            if not f.done():
                f.cancel()
        if futures:
            await asyncio.gather(*futures, return_exceptions=True)
        for env in INSTANCES:
            if env._private is not None:
                try:
                    await env.stop(delete=True)
                except Exception as e:
                    result['cleanup_errors'].append(type(e).__name__)
            for cmd in (['ps', '-aq'], ['network','ls','-q'], ['volume','ls','-q']):
                try:
                    if docker(*cmd, '--filter', 'label=searchswe.egress.instance='+env._instance).strip():
                        result['cleanup_errors'].append('owned resource remains')
                except Exception as e:
                    result['cleanup_errors'].append('inventory unverified: '+type(e).__name__)
        if receiver:
            receiver.shutdown();receiver.server_close()
        result['instances'] = [e.observation for e in INSTANCES]
        if result['cleanup_errors']:
            result['status'] = 'cleanup_error'
        (output / 'result.json').write_text(json.dumps(result, indent=2)+'\n')
        print(json.dumps({'status': result['status'], 'checks': len(result['checks']), 'error': result.get('error')}))
    return 0 if result['status'] == 'passed' else 2

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--gateway-image', default='searchswe-egress:dev10')
    parser.add_argument('--python-image', default='python:3.13-slim')
    parser.add_argument('--transport', choices=('proxy', 'direct'), default='proxy')
    raise SystemExit(asyncio.run(main(parser.parse_args())))
