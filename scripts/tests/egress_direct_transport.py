"""Offline direct HTTPS gate with real certificates and receiving-side evidence."""

import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import shlex
import ssl
import subprocess
import sys
import threading
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from harbor.models.task.config import EnvironmentConfig, NetworkPolicy
from harbor.models.trial.paths import TrialPaths
from scripts.harbor_environments import PhaseScopedDocker
from scripts.tests.egress_scenarios_fixture import DirectReceiver


CLIENT = '''import http.client,json,socket,ssl,sys,time
host,ip,port,sni=sys.argv[1:]
ctx=ssl.create_default_context(cafile='/tmp/origin.crt')
if sni=='none': ctx.check_hostname=False
try:
 with socket.create_connection((ip,int(port)),timeout=4) as sock:
  with ctx.wrap_socket(sock,server_hostname=None if sni=='none' else host) as tls:
   tls.sendall(f'GET /client/tls/{time.monotonic_ns()} HTTP/1.1\\r\\nHost: {host}:{port}\\r\\nConnection: close\\r\\n\\r\\n'.encode())
   response=http.client.HTTPResponse(tls);response.begin()
   print(json.dumps({'ok':response.status==200 and response.read()==b'OK','tls':tls.version()}))
except (OSError,http.client.HTTPException) as e:
 print(json.dumps({'ok':False,'error':type(e).__name__}))
'''


def docker(*args):
    return subprocess.run(['docker', *args], capture_output=True, text=True, check=True, timeout=60).stdout


async def run(args):
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    identity = 'searchswe-direct-tls-' + uuid.uuid4().hex[:12]
    result = {'status': 'running', 'identity': identity, 'checks': [], 'cleanup_errors': []}
    env, receiver = None, None
    try:
        result['sources'] = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in (
            Path(__file__), ROOT / 'scripts/tests/egress_scenarios_fixture.py',
            ROOT / 'scripts/harbor_environments.py', ROOT / 'environments/egress/gateway.py')}
        result['images'] = {role: json.loads(docker('image', 'inspect', name))[0]['Id']
                            for role, name in [('gateway', args.gateway_image), ('python', args.python_image)]}
        subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1',
                        '-subj', '/CN=allowed.example', '-addext',
                        'subjectAltName=DNS:allowed.example,DNS:blocked.example',
                        '-keyout', str(output / 'origin.key'), '-out', str(output / 'origin.crt')],
                       check=True, capture_output=True, timeout=30)
        (output / 'origin.key').chmod(0o600)
        bridge = json.loads(docker('network', 'inspect', 'bridge'))[0]['IPAM']['Config'][0]['Gateway']
        receiver = DirectReceiver((bridge, 0), output / 'receiver.jsonl')
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(output / 'origin.crt', output / 'origin.key')
        receiver.socket = context.wrap_socket(receiver.socket, server_side=True)
        threading.Thread(target=receiver.serve_forever, daemon=True).start()
        config = output / 'egress.json'
        config.write_text(json.dumps(receiver.configuration(args.gateway_image)))
        directory = output / 'environment'
        directory.mkdir()
        (directory / 'Dockerfile').write_text('FROM ' + args.python_image + '\n')
        both = NetworkPolicy(network_mode='allowlist', allowed_hosts=['allowed.example', 'blocked.example'])
        env = PhaseScopedDocker(environment_dir=directory, environment_name=identity, session_id=identity,
                                trial_paths=TrialPaths(trial_dir=output / 'trial'),
                                task_env_config=EnvironmentConfig(docker_image=args.python_image),
                                network_policy=both, egress_image=args.gateway_image,
                                egress_dns=receiver.configuration(args.gateway_image)['dns']['servers'][0])
        await env.start(force_build=False)
        client = output / 'client.py'
        client.write_text(CLIENT)
        await env.upload_file(client, '/tmp/client.py')
        await env.upload_file(output / 'origin.crt', '/tmp/origin.crt')

        async def probe(name, host, expected, *, destination='198.51.100.42', sni='hostname'):
            before = len(receiver.snapshot())
            response = await env.exec('python /tmp/client.py ' + shlex.join(
                [host, destination, str(receiver.server_address[1]), sni]))
            if response.return_code:
                raise RuntimeError('TLS client failed to report a result')
            client_result = json.loads(response.stdout)
            events = receiver.snapshot()[before:]
            reached = any(e.get('kind') == 'http' for e in events)
            if client_result['ok'] != expected or reached != expected:
                raise AssertionError('TLS authorization mismatch: ' + name)
            if not expected and events:
                raise AssertionError('rejected TLS hostname reached DNS or origin: ' + name)
            result['checks'].append({'case': name, 'passed': True, 'client': client_result, 'events': events})

        await probe('allowed-certificate-positive', 'allowed.example', True)
        await probe('forbidden-target-positive-control', 'blocked.example', True)
        await env.set_network_policy(NetworkPolicy(network_mode='allowlist', allowed_hosts=['allowed.example']))
        await probe('allowed-tls-after-restriction', 'allowed.example', True)
        await probe('blocked-sni-never-reaches-dns-or-origin', 'blocked.example', False)
        await probe('no-sni-rejected', 'allowed.example', False, sni='none')
        await env.set_network_policy(NetworkPolicy(network_mode='public'))
        await probe('public-tls-direct-positive', 'blocked.example', True, destination=bridge)
        await env.set_network_policy(NetworkPolicy(network_mode='no-network'))
        await probe('no-network-allowed-host-denied', 'allowed.example', False, destination=bridge)
        await probe('no-network-public-host-denied', 'blocked.example', False, destination=bridge)
        await env.set_network_policy(both)
        await probe('restored-policy-positive', 'allowed.example', True)
        result['status'] = 'passed'
    except BaseException as error:
        result.update(status='failed', error=type(error).__name__ + ': ' + str(error))
    finally:
        if env is not None:
            try:
                await env.stop(delete=True)
                for command in (['ps', '-aq'], ['network', 'ls', '-q'], ['volume', 'ls', '-q']):
                    if docker(*command, '--filter', 'label=searchswe.egress.instance=' + env._instance).strip():
                        raise RuntimeError('owned TLS gate resources remain')
            except Exception as error:
                result['cleanup_errors'].append(str(error))
        if receiver is not None:
            receiver.shutdown()
            receiver.server_close()
        if result['cleanup_errors']:
            result['status'] = 'cleanup_error'
        (output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
        print(json.dumps({'status': result['status'], 'checks': len(result['checks']), 'error': result.get('error')}))
    return 0 if result['status'] == 'passed' else 2


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gateway-image', required=True)
    parser.add_argument('--python-image', default='python:3.13-slim')
    parser.add_argument('--output', required=True, type=Path)
    raise SystemExit(asyncio.run(run(parser.parse_args())))
