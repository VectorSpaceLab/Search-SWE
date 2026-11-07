"""Prove arbitrary harness log names share the test's small disk quota."""
import errno
import json
import os
from pathlib import Path

root=Path('/logs/agent')
assert root.is_symlink() and root.stat().st_dev == Path('/app').stat().st_dev
assert os.getuid() == 10001
try:
    Path('/task-evidence/initialized').read_text()
except PermissionError:
    pass
else:
    raise AssertionError('Agent can read private development evidence')
path=root/'any-harness-quota-probe'
full=False
try:
    with path.open('wb',buffering=0) as output:
        for _ in range(128):
            output.write(b'x'*(1<<20))
except OSError as error:
    assert error.errno == errno.ENOSPC,error
    full=True
finally:
    path.unlink(missing_ok=True)
assert full,'Log output bypassed the 64 MiB integration-test filesystem'
(root/'quota-probe.json').write_text(json.dumps({'enospc':True,'same_filesystem':True,'private_evidence_denied':True}))
