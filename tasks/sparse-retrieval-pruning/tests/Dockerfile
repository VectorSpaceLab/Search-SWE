FROM docker.io/hanhainebula/search-swe-base:cpu-py3.12-1.0.0

ENV LITELLM_LOCAL_MODEL_COST_MAP=true

RUN /opt/conda/bin/python -m pip install --no-cache-dir \
    --index-url https://pypi.tuna.tsinghua.edu.cn/simple \
    --timeout 120 --retries 10 --resume-retries 10 \
    "harbor-rewardkit==0.2.0" "litellm==1.97.0"

ARG REWARDKIT_CODEX_VERSION=0.164.0
ARG REWARDKIT_CODEX_NPM_REGISTRY=https://registry.npmmirror.com
RUN set -eux; \
    root="/root/.cache/harbor-rewardkit/codex/${REWARDKIT_CODEX_VERSION}"; \
    npm install --global --registry="$REWARDKIT_CODEX_NPM_REGISTRY" \
      "@openai/codex@${REWARDKIT_CODEX_VERSION}"; \
    mkdir -p "$root/bin"; \
    ln -sf "$(command -v codex)" "$root/bin/codex"; \
    "$root/bin/codex" --version | grep -Fx "codex-cli ${REWARDKIT_CODEX_VERSION}"

RUN useradd --create-home --uid 10001 --shell /bin/bash submission \
    && /opt/conda/bin/python -c 'import ctypes, psutil; ctypes.CDLL("libseccomp.so.2")'

COPY . /tests/
COPY starter/ /baseline-starter/

RUN chmod 700 /tests /tests/data \
    && chmod 700 /tests/test.sh \
    && chmod 555 /baseline-starter /baseline-starter/src \
    && chmod 555 /baseline-starter/build.sh /baseline-starter/run.sh \
    && chmod 444 /baseline-starter/src/sparse_retrieval.py

# Login shells reset PATH to /usr/local/bin; keep all standard Python entry
# points on the provided Conda runtime, including NumPy and the verifier tools.
ENV OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
    NUMEXPR_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 BLIS_NUM_THREADS=1
RUN ln -sf /opt/conda/bin/python /usr/local/bin/python \
    && ln -sf /opt/conda/bin/python3 /usr/local/bin/python3 \
    && ln -sf /opt/conda/bin/python3.12 /usr/local/bin/python3.12 \
    && bash -lc 'python -c "import numpy; import sys; assert sys.prefix == \"/opt/conda\""' \
    && bash -lc 'python3 -c "import numpy; import sys; assert sys.prefix == \"/opt/conda\""'
