"""Read the fixed, losslessly compressed training arrays."""
import numpy as np

def load_training_array(path):
    if path.suffix == ".npz":
        with np.load(path, allow_pickle=False) as packed:
            if packed.files != ["values"]:
                raise ValueError("Unexpected training feature archive")
            return packed["values"]
    return np.load(path, mmap_mode="r", allow_pickle=False)
