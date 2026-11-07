FROM docker.io/hanhainebula/search-swe-base:gpu-cu13.0-py3.12-1.0.0
ENV HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 TOKENIZERS_PARALLELISM=false
ENV OMP_NUM_THREADS=16 OPENBLAS_NUM_THREADS=16 MKL_NUM_THREADS=16 NUMEXPR_NUM_THREADS=16
RUN /opt/conda/bin/python -m pip install --no-cache-dir --index-url https://pypi.tuna.tsinghua.edu.cn/simple "nvidia-ml-py==13.580.82"
RUN useradd --create-home --uid 10001 --user-group submission \
    && mkdir -p /app /task/data /task/models /task/runtime /task/docs /work \
    && chmod 0700 /task/models


COPY runtime/ /task/runtime/
COPY baselines/ /task/baselines/
RUN chmod -R a+rX /task/baselines
RUN find /task/runtime -type d -exec chmod 0555 {} + && find /task/runtime -type f -exec chmod 0444 {} +
WORKDIR /app
