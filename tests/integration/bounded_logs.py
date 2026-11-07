"""Offline real-Harbor log/ATIF/verifier checks on small FUSE filesystems.

Uses synthetic CLI executables with the native event formats. No model or judge
requests are made. Requires the formula task's root/FUSE host prerequisites.
"""
import argparse
import asyncio
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'src')]

from harbor.models.trial.config import TrialConfig, TaskConfig, AgentConfig, EnvironmentConfig
from harbor.models.trajectories.trajectory import Trajectory
from harbor.trial.single_step import SingleStepTrial
from scripts.evaluation.native_agents import agent_environment

SOURCE = ROOT / 'tasks/large-scale-formula-retrieval'
FIXTURES = Path(__file__).with_name('bounded_logs_fixture')
CASES = {'codex':('Codex','openai/gpt-4o',{'OPENAI_API_KEY':'fixture-no-api'}),
         'claude-code':('Claude','claude-sonnet-4-6',{'ANTHROPIC_API_KEY':'fixture-no-api'}),
         'pi':('IntegratedPi','openai/gpt-4o',{'OPENAI_API_KEY':'fixture-no-api'}),
         'pi-native':('NativePi','openai/gpt-4o',{'OPENAI_API_KEY':'fixture-no-api'}),
         'antigravity-cli':('Antigravity','gemini/gemini-2.5-flash',{'GEMINI_API_KEY':'fixture-no-api'}),
         'gemini-cli':('Gemini','gemini/gemini-2.5-flash',{'GEMINI_API_KEY':'fixture-no-api'})}


def prepare_task(work):
    task = work / 'task'
    shutil.copytree(SOURCE / 'environment', task / 'environment')
    (task / 'data').mkdir()
    tests = task / 'tests'; tests.mkdir()
    shutil.copyfile(SOURCE / 'tests/docker-compose.yaml', tests / 'docker-compose.yaml')
    for helper in ('integrity_gate.py', 'development.py'):
        shutil.copyfile(SOURCE / 'tests' / helper, tests / helper)
    (tests / 'Dockerfile').write_text('FROM hanhainebula/search-swe-base:cpu-py3.12-1.0.0\nCOPY . /tests/\nRUN chmod -R a+rX /tests && chmod 755 /tests/test.sh\n')
    (tests / 'test.sh').write_text('''#!/bin/bash
set -euo pipefail
cd /tests
/opt/conda/bin/python /tests/integrity_gate.py prepare
/opt/conda/bin/python - <<'CHECK'
import json
from pathlib import Path
trace=json.loads(Path('/logs/verifier/trajectory.json').read_text())
assert trace['schema_version'].startswith('ATIF-')
assert any(s['source']=='agent' for s in trace['steps'])
assert any(s.get('tool_calls') and s.get('observation') for s in trace['steps'])
assert Path('/app/submission/ready.txt').is_file()
evidence=Path('/task-evidence')
assert evidence.stat().st_mode & 0o077 == 0
record=json.loads((evidence/'agent.json').read_text())
from development import check_development
assert check_development()[1] is None
counts=dict(line.split() for line in record['memory_events'].splitlines())
assert int(counts['oom']) == int(counts['oom_kill']) == 0
Path('/logs/verifier/reward.txt').write_text('1.0')
Path('/logs/verifier/fixture.json').write_text(json.dumps({'synthetic_fixture':True,'model_requests':0,'private_memory_evidence':True,'atif_received':True}))
CHECK
''')
    (task / 'instruction.md').write_text('Write /app/submission/ready.txt and preserve a real fixture tool trace.\n')
    (task / 'task.toml').write_text('''schema_version="1.4"
artifacts=["/logs/agent/trajectory.json", "/app/submission"]
[task]
name="search-swe/bounded-log-fixture"
version="1.0.0"
[agent]
timeout_sec=30.0
user="submission"
network_mode="no-network"
[verifier]
timeout_sec=30.0
user="root"
environment_mode="separate"
network_mode="no-network"
[[verifier.collect]]
command="/opt/conda/bin/python /task/budget_evidence.py collect"
user="root"
timeout_sec=120.0
[environment]
build_timeout_sec=180.0
workdir="/app"
os="linux"
cpus=2
memory_mb=4096
storage_mb=65536
gpus=0
network_mode="no-network"
[environment.healthcheck]
command="/opt/conda/bin/python /task/budget_evidence.py setup"
timeout_sec=30.0
user="root"
''')
    shutil.copyfile(FIXTURES / 'cli.py', task / 'environment/fixture_cli.py')
    shutil.copyfile(FIXTURES / 'quota_probe.py', task / 'environment/quota_probe.py')
    with (task / 'environment/Dockerfile').open('a') as stream:
        stream.write('\nCOPY fixture_cli.py quota_probe.py /task/\nRUN chmod 755 /task/fixture_cli.py /task/quota_probe.py && for cli in codex claude pi gemini agy; do ln -sf /task/fixture_cli.py /usr/local/bin/$cli; done\n')
    return task


async def check(args):
    if os.getuid() != 0:
        raise ValueError('This integration check requires host root for FUSE preparation')
    work = args.output.resolve(); work.mkdir(parents=True, mode=0o700, exist_ok=False)
    task = prepare_task(work)
    runtime_root = work / 'storage'; runtime_root.mkdir()
    if args.tools_cache:
        shutil.copytree(args.tools_cache, runtime_root / '.tools')
    prepare = [sys.executable, str(SOURCE / 'tools/prepare_storage.py'), '--task-root', str(task), '--runtime-root', str(runtime_root)]
    records=[]
    with agent_environment({}):
        os.environ['FORMULA_CPUSET']=','.join(str(value) for value in sorted(os.sched_getaffinity(0))[:2])
        for case in args.agents:
            print('Checking:', case, flush=True)
            cls, model, env = CASES[case]
            env = {**env, **({'SEARCH_SWE_FIXTURE_OVERSIZE': '1'} if args.archive_failure else {})}
            subprocess.run([*prepare,'--run-id',case,'--probe-mib','64'],check=True,capture_output=True,text=True)
            os.environ['FORMULA_STORAGE_ROOT']=str(runtime_root/case)
            try:
                trial_name=case+'-'+uuid.uuid4().hex[:8]
                config=TrialConfig(task=TaskConfig(path=task),trial_name=trial_name,trials_dir=work/'trials',
                    agent=AgentConfig(import_path='tests.integration.bounded_logs_fixture.agents:'+cls,model_name=model,env=env),
                    environment=EnvironmentConfig(import_path='scripts.evaluation.harbor_environments:PhaseScopedDocker'))
                trial=await SingleStepTrial.create(config)
                result=await trial.run()
                path=work/'trials'/trial_name
                if args.archive_failure:
                    assert result.exception_info is not None
                    assert '512 MiB diagnostic reserve' in result.exception_info.exception_message
                    assert result.verifier is None and result.verifier_result is None
                    assert not (path/'verifier/fixture.json').exists()
                    assert '512 MiB diagnostic reserve' in (path/'bounded-logs-error.txt').read_text()
                    source=runtime_root/case/'agent/diagnostics/oversize.log'
                    assert source.stat().st_size == 1 << 30 and source.stat().st_blocks == 0
                    record={'agent':case,'oversized_archive_rejected':True,'source_retained':True,
                            'verifier_started':False,'model_requests':0,'synthetic_fixture':True}
                    records.append(record)
                    (work/'results.json').write_text(json.dumps(records,indent=2))
                    print(json.dumps(record),flush=True)
                    continue
                if result.exception_info:
                    raise RuntimeError(str(result.exception_info))
                assert result.verifier_result.rewards['reward']==1.0,result.verifier_result
                trace=Trajectory.model_validate_json((path/'agent/trajectory.json').read_text())
                assert len(trace.steps)>=2
                assert json.loads((path/'agent/harness.json').read_text())['source']=='trusted fixture metadata'
                assert not (path/'agent/outside-link').exists()
                assert not (path/'agent/blocked-pipe').exists()
                if case == 'antigravity-cli':
                    timestamps=json.loads((path/'agent/timestamp-probe.json').read_text())
                    assert timestamps['marker_mtime_ns'] == timestamps['transcript_mtime_ns']
                record={'agent':case,'real_harbor_lifecycle':True,'separate_verifier':True,'atif_steps':len(trace.steps),'model_requests':0,'synthetic_fixture':True}
                records.append(record)
                (work/'results.json').write_text(json.dumps(records,indent=2))
                print(json.dumps(record),flush=True)
            finally:
                subprocess.run([*prepare,'--run-id',case,'--unmount'],check=True,capture_output=True,text=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--tools-cache',type=Path,help='Existing verified formula-task .tools cache; copied for this check')
    parser.add_argument('--agents',nargs='+',choices=list(CASES),default=list(CASES))
    parser.add_argument('--archive-failure',action='store_true',help='Check oversized-log rejection without starting a verifier')
    asyncio.run(check(parser.parse_args()))


if __name__=='__main__':
    main()
