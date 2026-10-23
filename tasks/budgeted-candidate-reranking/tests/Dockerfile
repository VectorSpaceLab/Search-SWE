FROM docker.io/hanhainebula/search-swe-base:gpu-cu13.0-py3.12-1.0.0
ENV HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 TOKENIZERS_PARALLELISM=false
ENV OMP_NUM_THREADS=16 OPENBLAS_NUM_THREADS=16 MKL_NUM_THREADS=16 NUMEXPR_NUM_THREADS=16
RUN /opt/conda/bin/python -m pip install --no-cache-dir --index-url https://pypi.tuna.tsinghua.edu.cn/simple "nvidia-ml-py==13.580.82"
RUN useradd --create-home --uid 10001 --user-group submission \
    && mkdir -p /app /task/data /task/models /task/runtime /task/docs /work \
    && chmod 0700 /task/models

COPY . /tests/
RUN chmod 0700 /tests && chmod 0700 /tests/test.sh
WORKDIR /app
