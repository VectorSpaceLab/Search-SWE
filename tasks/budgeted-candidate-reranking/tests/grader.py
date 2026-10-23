"""Independent deterministic grader. All scoring state stays outside strategy UID."""
import gzip
import hashlib
import json
from scoring_parameters import SCORING
from pathlib import Path
import sys
import traceback

sys.path.insert(0, '/tests/runtime')
from evaluate import evaluate, dump
from isolation import cleanup
from submission_transfer import ARCHIVE, restore

OUTPUT = Path('/logs/verifier')


def anchors():
    data = SCORING
    b, u = float(data['baseline']), float(data['upper'])
    if not 0 <= b < u <= 1 or u-b < .01:
        raise RuntimeError('Missing, degenerate or uncalibrated scoring anchors')
    for name, expected in data['test_asset_sha256'].items():
        actual = hashlib.sha256((Path('/tests/data')/name).read_bytes()).hexdigest()
        if actual != expected:
            raise RuntimeError('Scoring anchor/input hash mismatch: '+name)
    with gzip.open('/tests/data/hidden.jsonl.gz', 'rt') as f:
        if sum(1 for _ in f) != 54:
            raise RuntimeError('All 54 official judged queries must be retained')
    return data


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    OUTPUT.chmod(0o700)
    (OUTPUT/'reward.txt').write_text('0\n')
    dump(OUTPUT/'reward.json', {'reward': 0.0})
    report = {'raw_reward': 0.0, 'score': 0.0, 'status': 'error', 'judge': 'pending_integrity_audit'}
    status = 1
    try:
        if Path(ARCHIVE).exists() or Path(ARCHIVE).is_symlink():
            restore()
        fixed = anchors()
        result = evaluate('/app/submission', '/tests/data/hidden.jsonl.gz',
                          '/tests/data/hidden-qrels.json', OUTPUT/'evaluation')
        if len(result['queries']) != 54:
            raise RuntimeError('Incomplete evaluation denominator')
        q, b, u = result['quality'], fixed['baseline'], fixed['upper']
        reward = max(0.0, min(1.0, (q-b)/(u-b)))
        report.update(result)
        report.update(raw_reward=reward, score=100*reward, baseline=b, upper=u,
                      initial_recall_at_100=fixed['initial_recall_at_100'],
                      status='complete', failed_queries=sum(r['status'] != 'ok' for r in result['queries']))
        status = 0
    except Exception as error:
        report['error'] = str(error)
        (OUTPUT/'exception.txt').write_text(traceback.format_exc())
    finally:
        try:
            cleanup()
        except Exception as error:
            report.update(raw_reward=0.0, score=0.0, status='error', error=str(error))
            status = 1
        dump(OUTPUT/'report.json', report)
    print(json.dumps({k: report[k] for k in ('status', 'raw_reward', 'score')}), flush=True)
    return status


if __name__ == '__main__':
    sys.exit(main())
