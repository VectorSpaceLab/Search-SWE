FROM docker.io/hanhainebula/search-swe-base:gpu-cu13.0-py3.12-1.0.0

RUN /opt/conda/bin/python -m pip install --no-cache-dir \
    --index-url https://pypi.tuna.tsinghua.edu.cn/simple \
    "bitsandbytes==0.50.2"

# Optional fixed-weight inference kernels; preserve the shared image's torch stack.
RUN /opt/conda/bin/python -m pip install --no-cache-dir --no-deps \
    --index-url https://pypi.tuna.tsinghua.edu.cn/simple \
    "gemlite==0.6.0.post2" "hqq==0.2.8.post1" "termcolor==3.3.0"

ENV HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 TOKENIZERS_PARALLELISM=false
RUN useradd --create-home --uid 10001 --user-group submission
COPY starter/ /app/submission/
RUN chmod 0755 /app/submission /app/submission/prepare.sh /app/submission/run.sh \
    && chmod 0644 /app/submission/submission.json
WORKDIR /app
