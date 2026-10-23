import json
import math
import os
from pathlib import Path

def main():
    p = Path('/logs/verifier')
    evaluation = json.loads((p / 'evaluation.json').read_text())
    audit = json.loads((p / 'audit.json').read_text()) if (p / 'audit.json').is_file() else {}
    passed = os.environ.get('JUDGE_STATUS') == '0' and audit.get('integrity') == 1
    metric = evaluation['deterministic_reward']
    if not isinstance(metric, (float, int)) or not math.isfinite(metric) or not 0 <= metric <= 1:
        raise ValueError('Invalid deterministic reward')
    reward = metric if passed else 0.0
    (p / 'reward.txt').write_text(f'{reward:.10f}\n')
    (p / 'reward.json').write_text(json.dumps({'reward': reward, 'primary_metric': metric, 'integrity': float(passed)}, allow_nan=False) + '\n')
    (p / 'judge-status.json').write_text(json.dumps({'exit_status': os.environ.get('JUDGE_STATUS'), 'passed': passed}) + '\n')
    if not passed:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
