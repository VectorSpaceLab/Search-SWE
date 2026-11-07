FROM docker.io/hanhainebula/search-swe-base:gpu-cu13.0-py3.12-1.0.0

RUN /opt/conda/bin/python -m pip install --no-cache-dir --index-url https://pypi.tuna.tsinghua.edu.cn/simple "nvidia-ml-py==13.580.82" "peft==0.20.0"
RUN useradd --create-home --uid 10001 --user-group submission \
    && mkdir -p /app /task/corpus /task/models /task/runtime /task/public /task/docs
COPY runtime/ /task/runtime/
COPY docs/ /task/docs/
RUN chmod -R a+rX /task
ENV OMP_NUM_THREADS=16 OPENBLAS_NUM_THREADS=16 MKL_NUM_THREADS=16 TOKENIZERS_PARALLELISM=false HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_HOME=/app/.cache/huggingface XDG_CACHE_HOME=/app/.cache TORCH_HOME=/app/.cache/torch TRITON_CACHE_DIR=/app/.cache/triton
WORKDIR /app
