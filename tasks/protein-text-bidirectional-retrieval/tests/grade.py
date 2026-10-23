import json
from pathlib import Path
import sys

sys.path.insert(0, '/task/runtime')
from evaluate import evaluate
from isolation import cleanup
from submission_transfer import restore


def main():
    output = Path('/logs/verifier'); output.mkdir(parents=True, exist_ok=True)
    report = {'valid': False, 'reward': 0.0}
    try:
        restore()
        report = evaluate('/task/private', output, full_queries=True)
    except Exception as exc:
        report = {'valid': False, 'reward': 0.0, 'failure': type(exc).__name__ + ': ' + str(exc)}
        print(report['failure'], file=sys.stderr)
    finally:
        cleanup()
    (output / 'report.json').write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
    return 0 if report['valid'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
