"""Draft isolated vector adapter; each invocation has exactly one phase."""
import contextlib
import importlib.util
import json
import os
from pathlib import Path
import sys

from isolation import isolate


def main():
    import numpy as np
    import torch

    work = Path(os.environ['RETRIEVAL_WORK_DIR'])
    torch.set_num_threads(16)
    torch.manual_seed(0)
    torch.cuda.init()
    isolate(work)
    synchronize = torch.cuda.synchronize
    emit, flush = sys.stdout.write, sys.stdout.flush
    init = json.loads(sys.stdin.readline())

    def array(value, count):
        if isinstance(value, torch.Tensor):
            if value.is_complex() or value.dtype == torch.bool:
                raise ValueError('encode must return real numeric values')
            value = value.detach().to(device='cpu', dtype=torch.float32).numpy()
        value = np.asarray(value)
        if value.shape != (count, 64) or value.dtype.kind not in 'fiu':
            raise ValueError('encode must return an N-by64 numeric array')
        with np.errstate(over='ignore', invalid='ignore'):
            value = value.astype(np.float32)
        if not np.isfinite(value).all():
            raise ValueError('encode must return finite float32 values')
        return value.tolist()

    with contextlib.redirect_stdout(sys.stderr):
        sys.path.insert(0, '/app/submission')
        spec = importlib.util.spec_from_file_location('submission_encoder', '/app/submission/encoder.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        encoder = module.Encoder(model_root='/task/models', checkpoint_root='/app/submission', work_dir=str(work))
        if init['phase'] == 'candidates':
            values = [json.loads(line)['value'] for line in (work / 'candidates.jsonl').read_text().splitlines()]
            with torch.inference_mode():
                vectors = array(encoder.encode(values, init['modality']), len(values))
            synchronize()
        elif init['phase'] == 'queries':
            synchronize()
        else:
            raise ValueError('Unknown trusted encoder phase')
    if init['phase'] == 'candidates':
        emit(json.dumps({'ready': True, 'vectors': vectors}, allow_nan=False, separators=(',', ':')) + '\n')
        flush()
        return

    emit('{"ready":true}\n'); flush()
    for line in sys.stdin:
        try:
            request = json.loads(line)
            with contextlib.redirect_stdout(sys.stderr), torch.inference_mode():
                result = encoder.encode([request['query']], init['modality'])
                vector = None if result is None else array(result, 1)[0]
                synchronize()
            response = {'vector': vector}
        except Exception as exc:
            synchronize()
            response = {'error': type(exc).__name__ + ': ' + str(exc)[:1000]}
        emit(json.dumps(response, allow_nan=False, separators=(',', ':')) + '\n'); flush()


if __name__ == '__main__':
    main()
