
# `apex_topk`: Accelerated top-_k_ operators for PyTorch

A [pytorch](https://pytorch.org)
[CUDA](https://developer.nvidia.com/cuda-zone)/[C++](https://cppreference.com)
extension module for accelerating top-_k_ retrieval from combinatorial
synthesis libraries.

## Building

To build the **apex_topk** extension module, you will first need to
install PyTorch (and any relevant compiler toolchains),
```bash
pip install torch
```

### With CUDA
When building the extension of a CUDA-capable machine, you will first
need to download CCCL into this folder (same level as this `README.md`)
```bash
git clone https://github.com/NVIDIA/cccl.git
```

### Without CUDA
To skip building the CUDA operators, modify the `build_cuda` variable
inside the [setup.py](setup.py) file before running the following
commands.

### Testing
Tests are organized into the [test](test) directory.
```bash
pytest -v test
```

### Packaging
Then build and install the wheel,
```bash
pip install wheel
python3 setup.py build
python3 setup.py bdist_wheel
pip install dist/*.whl
```

## Licensing

The **apex_topk** extension module is released under the
[MIT license](https://opensource.org/licenses/MIT). See the
[LICENSE.md](LICENSE.md) file for the complete license terms.

