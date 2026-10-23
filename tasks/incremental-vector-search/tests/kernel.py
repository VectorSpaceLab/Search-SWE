"""Identify the actual float32 distance implementation, not a CPU model."""
from functools import lru_cache
import hashlib
import importlib
import json
from pathlib import Path

import faiss
import numpy as np


@lru_cache(maxsize=1)
def kernel_signature():
    wrapper = importlib.import_module(faiss.fvec_L2sqr.__module__)
    binary = getattr(wrapper, "_" + wrapper.__name__.rsplit(".", 1)[-1])
    with Path(binary.__file__).open("rb") as stream:
        binary_hash = hashlib.file_digest(stream, "sha256").hexdigest()
    rng = np.random.Generator(np.random.PCG64(260306660))
    vectors = rng.random((9, 3072), dtype=np.float32)
    probe = np.asarray([faiss.fvec_L2sqr(faiss.swig_ptr(vectors[0]),
                        faiss.swig_ptr(vectors[i]), dim)
                        for dim in (1536, 3072) for i in range(1, 9)], dtype="<f4")
    return {"faiss_version": faiss.__version__, "compile_options": faiss.get_compile_options().strip(),
            "binary_sha256": binary_hash,
            "probe_sha256": hashlib.sha256(probe.tobytes()).hexdigest()}


def require_truth_kernel(private):
    manifest = json.loads((private / "truth-manifest.json").read_text())
    if manifest.get("runtime_signature") != kernel_signature():
        raise RuntimeError("Exact targets use a different Faiss runtime; regenerate targets inside "
                           "the verifier image in the evaluation environment")
