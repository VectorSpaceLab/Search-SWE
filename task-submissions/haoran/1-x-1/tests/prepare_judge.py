import json
import os
from pathlib import Path

p = Path("/logs/verifier/.private/judge-bin")
p.mkdir(parents=True, exist_ok=True)
f = p / "codex"
f.write_text('#!/bin/bash\nexec /opt/conda/bin/python -I /tests/judge_fs.py "$@"\n')
f.chmod(0o700)

home = Path(os.environ["CODEX_HOME"])
base = os.environ.get("OPENAI_BASE_URL", "").rstrip("/")
if not base or not os.environ.get("OPENAI_API_KEY"):
    raise RuntimeError("Trajectory judge credentials are required")
config = (
    'model_provider = "trajectory_judge"\napproval_policy = "never"\nsandbox_mode = "danger-full-access"\n[model_providers.trajectory_judge]\nname = "Trajectory judge"\nbase_url = '
    + json.dumps(base)
    + '\nwire_api = "responses"\nenv_key = "OPENAI_API_KEY"\nsupports_websockets = false\n'
)
(home / "config.toml").write_text(config)
(home / "config.toml").chmod(0o600)
