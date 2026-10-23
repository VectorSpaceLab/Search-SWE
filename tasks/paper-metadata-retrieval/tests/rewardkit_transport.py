"""Keep recovered Codex stream reconnects from invalidating a finished audit.

Compatibility launcher for RewardKit 0.2.0. The backend still rejects nonzero
process exits, missing responses and invalid judge output using its own checks.
"""
from functools import wraps
import json
import runpy
import sys


def recovered_reconnections(raw):
    reconnects = []
    completed = False
    for line in raw.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict):
            continue
        kind = event.get("type")
        if kind == "error":
            message = event.get("message", "")
            if not (isinstance(message, str)
                    and message.startswith("Reconnecting... ")
                    and "stream disconnected before completion:" in message):
                return []
            reconnects.append(message)
            completed = False
        elif kind == "turn.failed":
            return []
        elif kind == "turn.started":
            completed = False
        elif kind == "turn.completed":
            completed = True
    return reconnects if completed else []


def with_stream_recovery(metadata):
    @wraps(metadata)
    def wrapped(self, raw, label):
        output, usage, log, warnings, error = metadata(self, raw, label)
        recovered = recovered_reconnections(raw)
        if error and error in recovered:
            warnings = [*warnings, (
                f"Recovered {len(recovered)} Codex stream reconnect event(s) "
                f"before turn.completed; original event: {error}"
            )]
            error = None
        return output, usage, log, warnings, error
    return wrapped


if __name__ == "__main__":
    from rewardkit.agents import CodexBackend

    CodexBackend._metadata = with_stream_recovery(CodexBackend._metadata)
    sys.argv = sys.argv[1:]
    runpy.run_path(sys.argv[0], run_name="__main__")
