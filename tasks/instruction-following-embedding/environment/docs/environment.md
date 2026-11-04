# Environment

The task uses Python 3.12 at /opt/conda/bin/python with CUDA-enabled PyTorch, Transformers, PEFT, NumPy, and safetensors. One NVIDIA A100 with 40 GiB GPU memory is available, together with 16 CPU cores, 32 GiB RAM, and 32 GiB task storage.

Task data and the supplied backbone are mounted read-only under /task/data, /task/public, /task/corpus, and /task/models. Public evaluation tools and the baseline script are read-only under /task/runtime and /task/baselines. Work under /app.
