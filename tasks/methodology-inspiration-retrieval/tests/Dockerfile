FROM docker.io/hanhainebula/search-swe-base:gpu-cu13.0-py3.12-1.0.0

ENV LITELLM_LOCAL_MODEL_COST_MAP=true

RUN /opt/conda/bin/python -m pip install --no-cache-dir \
    --index-url https://pypi.tuna.tsinghua.edu.cn/simple \
    --timeout 120 --retries 10 --resume-retries 10 \
    "harbor-rewardkit==0.2.0" \
    "litellm==1.97.0"

ARG REWARDKIT_CODEX_VERSION=0.147.0
ARG REWARDKIT_CODEX_NPM_REGISTRY=https://registry.npmmirror.com
RUN set -eux; \
    root="/root/.cache/harbor-rewardkit/codex/${REWARDKIT_CODEX_VERSION}"; \
    npm install --global --registry="$REWARDKIT_CODEX_NPM_REGISTRY" \
      "@openai/codex@${REWARDKIT_CODEX_VERSION}"; \
    mkdir -p "$root/bin"; \
    ln -sf "$(command -v codex)" "$root/bin/codex"; \
    "$root/bin/codex" --version | grep -Fx "codex-cli ${REWARDKIT_CODEX_VERSION}"

RUN useradd --create-home --uid 10001 --user-group submission

# Isolate the supplied model's Transformers 4 runtime from the shared image.
RUN /opt/conda/bin/python -m venv --system-site-packages /opt/stella \
    && /opt/stella/bin/python -m pip install --no-cache-dir \
        --index-url https://pypi.tuna.tsinghua.edu.cn/simple \
        --timeout 120 --retries 5 \
        "transformers==4.44.2" "tokenizers==0.19.1" \
        "huggingface-hub==0.36.0" "sentence-transformers==3.0.1" "einops==0.8.1" "peft==0.12.0"

COPY . /tests/

RUN chmod 700 /tests \
    && chmod 700 /tests/test.sh
