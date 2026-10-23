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

COPY . /tests/

RUN chmod 700 /tests /tests/test.sh /tests/*.py \
    && chmod 700 /tests/data \
    && chmod 600 /tests/data/queries.jsonl /tests/data/qrels_gold.txt \
    && test "$(wc -l < /tests/data/queries.jsonl)" -eq 20 \
    && test "$(wc -l < /tests/data/qrels_gold.txt)" -eq 63
