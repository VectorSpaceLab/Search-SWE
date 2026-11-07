FROM docker.io/hanhainebula/search-swe-base:gpu-cu13.0-py3.12-1.0.0
RUN /opt/conda/bin/python -m pip install --no-cache-dir --index-url https://pypi.tuna.tsinghua.edu.cn/simple "nvidia-ml-py==13.580.82"
RUN useradd --create-home --uid 10001 --user-group submission && mkdir -p /app /task/runtime /task/docs /task/baselines /opt/harbor
COPY runtime/ /task/runtime/
COPY docs/ /task/docs/
COPY baselines/ /task/baselines/
ENV SEARCH_SWE_AGENT_CONTAINER=1 OMP_NUM_THREADS=16 OPENBLAS_NUM_THREADS=16 MKL_NUM_THREADS=16 PYTHONDONTWRITEBYTECODE=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 XDG_CACHE_HOME=/app/.cache
WORKDIR /app
