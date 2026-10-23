"""Keep a build process family observable until its supervisor stops it."""
import json
import subprocess
import sys

request = json.loads(sys.stdin.readline())
result = subprocess.run(request['command'], stdin=subprocess.DEVNULL, stdout=sys.stderr)
print(json.dumps({'ok': result.returncode == 0, 'returncode': result.returncode}), flush=True)
sys.stdin.readline()
