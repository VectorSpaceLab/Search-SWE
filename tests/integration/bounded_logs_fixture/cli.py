#!/opt/conda/bin/python
"""Synthetic CLI protocol fixture: no model calls; run real Harbor adapters."""
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

name = Path(sys.argv[0]).name
if name == 'agy' and sys.argv[1:] == ['models']:
    print(json.dumps({'models': []})); sys.exit(0)
if '--version' in sys.argv:
    print({'codex':'codex-cli 0.164.0','claude':'2.1.309 (Claude Code)','pi':'1.4.0','gemini':'0.67.0','agy':'1.5.2'}[name]);sys.exit(0)
assert os.getuid() == 10001
root = Path('/logs/agent')
assert root.is_symlink() and root.stat().st_dev == Path('/app').stat().st_dev
if name == 'claude':
    prompt = sys.stdin.read()
elif name == 'codex':
    prompt = sys.argv[sys.argv.index('--') + 1]
elif name in ('gemini', 'agy'):
    prompt = next(item.split('=',1)[1] for item in sys.argv if item.startswith('--prompt='))
else:
    prompt = sys.argv[-1]
session = str(uuid.uuid4())
timestamp = '2026-11-07T00:00:00Z'
submission = Path('/app/submission'); submission.mkdir(exist_ok=True)
(submission / 'ready.txt').write_text(name)
(root / 'original.log').write_text('fixture log')
(root / 'linked.log').hardlink_to(root / 'original.log')
(root / 'outside-link').symlink_to('/task-evidence/initialized')
os.mkfifo(root / 'blocked-pipe')
(root / 'harness.json').write_text('{"source":"untrusted override"}')
(root / 'trajectory.json').write_text('{"source":"untrusted ATIF"}')
background = subprocess.Popen(['sleep', '120'], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
(root / 'background.pid').write_text(str(background.pid))
if os.environ.get('SEARCH_SWE_FIXTURE_OVERSIZE'):
    with (root / 'oversize.log').open('wb') as output:
        output.truncate(1 << 30)  # No allocated data blocks; unsafe to expand.

def jsonl(path, records):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(''.join(json.dumps(record)+'\n' for record in records))

if name == 'codex':
    rows = [{'type':'session_meta','payload':{'id':session,'timestamp':timestamp,'cwd':'/app','cli_version':'0.164.0'}}]
    for role, text in [('user',prompt),('assistant','fixture completed')]:
        rows.append({'type':'response_item','timestamp':timestamp,'payload':{'type':'message','role':role,'content':[{'type':'input_text' if role=='user' else 'output_text','text':text}]}})
    rows[2:2] = [
      {'type':'response_item','timestamp':timestamp,'payload':{'type':'function_call','call_id':'fixture-call','name':'exec_command','arguments':'{"cmd":"write ready.txt"}'}},
      {'type':'response_item','timestamp':timestamp,'payload':{'type':'function_call_output','call_id':'fixture-call','output':'ready'}}]
    jsonl(Path(os.environ['CODEX_HOME'])/'sessions/2026/11/07'/f'rollout-{session}.jsonl', rows)
elif name == 'claude':
    common={'sessionId':session,'version':'2.1.309','cwd':'/app','timestamp':timestamp}
    rows=[{**common,'type':'user','uuid':'u1','message':{'role':'user','content':prompt}},
          {**common,'type':'assistant','uuid':'a1','message':{'id':'msg1','role':'assistant','model':'claude-sonnet-4-6','content':[{'type':'tool_use','id':'fixture-call','name':'Bash','input':{'command':'write ready.txt'}}]}},
          {**common,'type':'user','uuid':'u2','message':{'role':'user','content':[{'type':'tool_result','tool_use_id':'fixture-call','content':'ready'}]}},
          {**common,'type':'assistant','uuid':'a2','message':{'id':'msg2','role':'assistant','model':'claude-sonnet-4-6','content':[{'type':'text','text':'fixture completed'}]}}]
    jsonl(Path(os.environ['CLAUDE_CONFIG_DIR'])/'projects'/'-app'/f'{session}.jsonl',rows)
elif name == 'pi':
    session_dir=Path(sys.argv[sys.argv.index('--session-dir')+1]); session_dir.mkdir(parents=True,exist_ok=True)
    rows=[{'type':'session','id':session}]
    for msg in [{'role':'user','content':[{'type':'text','text':prompt}]},
                {'role':'assistant','content':[{'type':'toolCall','id':'fixture-call','name':'bash','arguments':{'command':'write ready.txt'}}],'stopReason':'toolUse'},
                {'role':'toolResult','toolCallId':'fixture-call','content':[{'type':'text','text':'ready'}]},
                {'role':'assistant','content':[{'type':'text','text':'fixture completed'}],'stopReason':'stop'}]:
        rows.append({'type':'message_end','message':msg})
    jsonl(session_dir/f'{session}.jsonl',rows)
    for row in rows: print(json.dumps(row))
elif name == 'agy':
    rows=[{'type':'USER_INPUT','step_index':0,'created_at':timestamp,'content':prompt},
          {'type':'PLANNER_RESPONSE','step_index':1,'created_at':timestamp,'content':'working','tool_calls':[{'name':'run_command','args':{'command':'write ready.txt'}}]},
          {'type':'RUN_COMMAND','step_index':2,'created_at':timestamp,'content':'ready','status':'SUCCESS'},
          {'type':'PLANNER_RESPONSE','step_index':3,'created_at':timestamp,'content':'fixture completed'}]
    transcript = Path.home()/'.gemini/antigravity-cli/brain'/session/'.system_generated/logs/transcript_full.jsonl'
    jsonl(transcript, rows)
    # Force the native marker and transcript to have equal timestamps, as can
    # occur on fuse2fs even when the transcript was written later.
    marker = Path('/tmp/.harbor-antigravity-run-start').stat()
    os.utime(transcript, ns=(marker.st_atime_ns, marker.st_mtime_ns))
    (root / 'timestamp-probe.json').write_text(json.dumps({
        'marker_mtime_ns': marker.st_mtime_ns,
        'transcript_mtime_ns': transcript.stat().st_mtime_ns}))
else:
    payload={'sessionId':session,'messages':[{'type':'user','timestamp':timestamp,'content':prompt},
        {'type':'gemini','timestamp':timestamp,'model':'gemini-2.5-flash','content':'fixture completed','toolCalls':[{'id':'fixture-call','name':'run_shell_command','args':{'command':'write ready.txt'},'result':[{'functionResponse':{'response':{'output':'ready'}}}]}]}]}
    path=Path.home()/'.gemini/tmp/fixture/chats/session-fixture.json';path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(payload))
print('fixture completed')
