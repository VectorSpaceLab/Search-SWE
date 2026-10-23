"""Trusted transform invoker: isolate first, then load only submitted code."""
import argparse
import contextlib
import importlib.util
import json
import os
from pathlib import Path
import sys

import numpy as np
from isolation import isolate

LANGUAGES = {"ar", "zh", "en", "fr", "hi", "it", "ja", "pt", "ru", "es"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--submission", required=True)
    parser.add_argument("--work", required=True)
    parser.add_argument("--isolate", action="store_true")
    parser.add_argument("--require-gpu", action="store_true")
    args = parser.parse_args()
    submission = Path(args.submission).resolve()
    work = Path(args.work).resolve()
    try:
        Path("/proc/self/oom_score_adj").write_text("500")
    except OSError:
        pass
    # Establish the trusted CUDA driver context before restricting OS calls.
    # No submitted code/weights, hidden data, or service keys are loaded here.
    import torch
    if args.require_gpu:
        if torch.cuda.device_count() != 1 or "A100" not in torch.cuda.get_device_name(0):
            raise RuntimeError("Exactly one A100 GPU is required")
        memory = torch.cuda.get_device_properties(0).total_memory
        if not 39e9 < memory < 44e9:
            raise RuntimeError("The A100 must have 40GB physical memory")
        torch.cuda.init()
        # Keep the trusted C entrypoint before submitted imports can replace
        # Python attributes such as torch.cuda.synchronize.
        synchronize = torch._C._cuda_synchronize
    else:
        synchronize = lambda: None
    if args.isolate:
        if os.environ.get("SEARCH_SWE_VERIFIER_SANDBOX") != "1":
            raise RuntimeError("Isolation must run inside the disposable verifier container")
        isolate(work)
    else:
        os.chdir(work)
    # Do not import submitted Python or deserialize its weights before isolation.
    sys.path.insert(0, str(submission))
    spec = importlib.util.spec_from_file_location("submission_transform", submission / "transform.py")
    module = importlib.util.module_from_spec(spec)
    with contextlib.redirect_stdout(sys.stderr), torch.inference_mode():
        spec.loader.exec_module(module)
        state = module.load(str(submission))
        synchronize()
    print('{"ready":true}', flush=True)
    for line in sys.stdin:
        try:
            request = json.loads(line)
            if set(request) != {"vectors", "languages"}:
                raise ValueError("Unexpected transform inputs")
            vectors = np.asarray(request["vectors"], dtype=np.float32)
            languages = request["languages"]
            if vectors.ndim != 2 or vectors.shape[1] != 1024 or not 1 <= len(vectors) <= 128:
                raise ValueError("Expected a 1..128 by 1024 matrix")
            if len(languages) != len(vectors) or any(x not in LANGUAGES for x in languages) or not np.isfinite(vectors).all():
                raise ValueError("Invalid transform inputs")
            vectors.setflags(write=False)
            with contextlib.redirect_stdout(sys.stderr), torch.inference_mode():
                result = module.transform(vectors, languages, state)
                if isinstance(result, torch.Tensor):
                    if result.is_complex():
                        raise ValueError("Transform must return real vectors")
                    result = result.detach().float().cpu().numpy()
                if not np.isrealobj(result):
                    raise ValueError("Transform must return real vectors")
                result = np.asarray(result, dtype=np.float32)
                synchronize()
            if result.shape != vectors.shape or not np.isfinite(result).all():
                raise ValueError("Invalid transformed matrix")
            print(json.dumps({"vectors": result.tolist()}, allow_nan=False, separators=(",", ":")), flush=True)
        except Exception as error:
            print(json.dumps({"error": type(error).__name__}), flush=True)


if __name__ == "__main__":
    main()
