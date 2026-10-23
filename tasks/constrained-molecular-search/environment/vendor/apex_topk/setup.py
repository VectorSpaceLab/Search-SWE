# Standard
import os

# Third party
from setuptools import find_packages, setup
from torch.utils.cpp_extension import (
    BuildExtension,
    CppExtension,
    CUDAExtension,
)

build_cuda = True

if build_cuda:
    os.environ["TORCH_CUDA_ARCH_LIST"] = "8.0"
    ext = CUDAExtension(
        name="apex_topk._ops",
        language="c++",
        include_dirs=[
            "include",
            "cccl/cub",
            "cccl/thrust",
            "cccl/libcudacxx/include",
        ],
        sources=[
            "src/library.cc",
            "src/impl-cpu.cc",
            "src/impl-cuda.cu",
        ],
        extra_compile_args={
            "cxx": ["-O2"],
            "nvcc": ["-O2"],
        },
    )
else:
    ext = CppExtension(
        name="apex_topk._ops",
        language="c++",
        include_dirs=["include"],
        sources=[
            "src/library.cc",
            "src/impl-cpu.cc",
        ],
        extra_compile_args={"cxx": ["-O2"]},
    )

build_ext = BuildExtension.with_options(
    no_python_abi_suffix=True,
    use_ninja=False,
)

setup(
    name="apex_topk",
    version="1.0.0",

    author="Bradley Worley, Darren Hsu",
    author_email="brad@atomwise.com, dahsu@nvidia.com",
    description="Accelerated top-k operators for APEX",
    long_description=(
        "A PyTorch CUDA/C++ extension module "
        "for AProximate EXhaustive screening"
    ),

    packages=find_packages(),
    ext_modules=[ext],
    cmdclass={"build_ext": build_ext},

    install_requires=["torch>=2.5.1"],
)
