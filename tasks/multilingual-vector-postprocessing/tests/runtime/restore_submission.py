"""Trusted restoration from post-agent collected artifacts into fresh tmpfs."""
import json
import os
from pathlib import Path
import shutil
import sys

sys.path.insert(0, "/task/runtime")
from evaluate import verify_snapshot


def main():
    if os.environ.get("SEARCH_SWE_VERIFIER_SANDBOX") != "1":
        raise RuntimeError("Restore only in the independent verifier container")
    source = Path("/logs/agent/collected-submission")
    metadata = Path("/logs/agent/submission-freeze-status.json")
    destination = Path("/app/submission")
    status = dict(valid=False, files=[], reason="Missing trusted collected artifact")
    try:
        if metadata.is_symlink() or not metadata.is_file():
            raise ValueError("Missing regular collection status")
        status = json.loads(metadata.read_text())
        # Verify every regular file and exact manifest coverage before copying;
        # do not follow submitted links or mutate read-only framework mounts.
        verify_snapshot(source, metadata, make_read_only=False)
        if destination.is_symlink():
            destination.unlink()
        elif destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(source, destination)
    except Exception as error:
        status = dict(valid=False, files=[], reason="Collected artifact restoration failed: " + str(error))
        if destination.is_symlink():
            destination.unlink()
        elif destination.exists():
            shutil.rmtree(destination)
        destination.mkdir()
    Path("/var/tmp/submission-freeze-status.json").write_text(json.dumps(status, indent=2))


if __name__ == "__main__":
    main()
