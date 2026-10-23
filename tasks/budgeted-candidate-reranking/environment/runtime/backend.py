"""Root-only fixed backend. Its pipes are never inherited by strategy code."""
import json
import sys
from model import FixedModel, Meter, deployment_config


def main():
    model = FixedModel(deployment_config(sys.argv[1]))
    print(json.dumps({'ready': True, 'model': model.info}), flush=True)
    for line in sys.stdin:
        job = json.loads(line)
        meter = Meter(job['budget'])
        meter.spent = job['already_spent']
        try:
            request = job['request']
            count_only = isinstance(request, dict) and request.get('type') == 'count'
            if count_only:
                request = {**request, 'type': 'generate'}
            prepared = model.prepare(request, set(job['candidate_ids']))
            if count_only:
                reply = {'type': 'count', 'input_tokens': len(prepared[0]),
                         'reserved_cost': len(prepared[0]) + 4*prepared[1],
                         'remaining_tokens': meter.budget-meter.spent}
            else:
                reply = model.generate(prepared, meter, lambda r: print(
                    json.dumps({'reservation': r, 'meter_spent': meter.spent}), flush=True))
            response = {'reply': reply, 'meter_spent': meter.spent,
                        'calls': meter.calls, 'model': model.info}
        except Exception as error:
            response = {'error': str(error), 'meter_spent': meter.spent,
                        'calls': meter.calls, 'model': model.info}
        print(json.dumps(response, allow_nan=False), flush=True)


if __name__ == '__main__':
    main()
