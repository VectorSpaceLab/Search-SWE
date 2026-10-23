"""Fail-closed task-specific evaluator, separate from trajectory integrity review."""
import json
from scoring_parameters import SCORING
from pathlib import Path
import sys

sys.path.insert(0,'/task/runtime')
from evaluate import evaluate
from isolation import cleanup
from submission_transfer import restore

OUT=Path('/logs/verifier')


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    report={'valid':False,'reward':0.}
    try:
        restore()
        anchors=SCORING
        groups=json.loads(Path('/tests/data/groups.json').read_text())
        report=evaluate(groups,OUT,anchors)
    except Exception as exc:
        report={'valid':False,'reward':0.,'failure':type(exc).__name__+': '+str(exc)}
        print(report['failure'],file=sys.stderr)
    finally:cleanup()
    (OUT/'report.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    return 0 if report['valid'] else 1

if __name__=='__main__':raise SystemExit(main())
