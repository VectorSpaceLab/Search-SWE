FROM docker.io/hanhainebula/search-swe-base:cpu-py3.12-1.0.0

ENV LITELLM_LOCAL_MODEL_COST_MAP=true

RUN /opt/conda/bin/python -m pip install --no-cache-dir \
    --index-url https://pypi.tuna.tsinghua.edu.cn/simple \
    --timeout 120 --retries 10 --resume-retries 10 \
    "harbor-rewardkit==0.2.0" \
    "litellm==1.97.0"

ARG REWARDKIT_CODEX_VERSION=0.164.0
ARG REWARDKIT_CODEX_NPM_REGISTRY=https://registry.npmmirror.com
RUN set -eux; \
    root="/root/.cache/harbor-rewardkit/codex/${REWARDKIT_CODEX_VERSION}"; \
    npm install --global --registry="$REWARDKIT_CODEX_NPM_REGISTRY" \
      "@openai/codex@${REWARDKIT_CODEX_VERSION}"; \
    mkdir -p "$root/bin"; \
    ln -sf "$(command -v codex)" "$root/bin/codex"; \
    "$root/bin/codex" --version | grep -Fx "codex-cli ${REWARDKIT_CODEX_VERSION}"

RUN useradd --create-home --uid 10001 --user-group submission
RUN mkdir -p /task/private && chmod 700 /task/private
RUN /opt/conda/bin/python -c 'import faiss,numpy,pyarrow,psutil; import ctypes; ctypes.CDLL("libseccomp.so.2")'
COPY *.py test.sh /tests/
COPY data/queries.f32 data/queries.jsonl data/qrels.tsv /task/private/data/
RUN chmod 700 /tests /tests/test.sh /task/private/data \
    && chmod 600 /task/private/data/*

COPY integrity_judge/ /audit/integrity_judge/
RUN chmod -R go-rwx /audit
