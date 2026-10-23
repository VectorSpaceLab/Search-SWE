FROM docker.io/hanhainebula/search-swe-base:gpu-cu13.0-py3.12-1.0.0
ENV LITELLM_LOCAL_MODEL_COST_MAP=true
RUN /opt/conda/bin/python -m pip install --no-cache-dir \
    --index-url https://pypi.tuna.tsinghua.edu.cn/simple \
    "harbor-rewardkit==0.2.0" "litellm==1.97.0" "nvidia-ml-py==13.580.82" "peft==0.20.0"
ARG REWARDKIT_CODEX_VERSION=0.164.0
ARG REWARDKIT_CODEX_NPM_REGISTRY=https://registry.npmmirror.com
RUN set -eux; \
    root="/root/.cache/harbor-rewardkit/codex/${REWARDKIT_CODEX_VERSION}"; \
    npm install --global --registry="$REWARDKIT_CODEX_NPM_REGISTRY" \
      "@openai/codex@${REWARDKIT_CODEX_VERSION}"; \
    mkdir -p "$root/bin"; \
    ln -sf "$(command -v codex)" "$root/bin/codex"; \
    "$root/bin/codex" --version | grep -Fx "codex-cli ${REWARDKIT_CODEX_VERSION}"
# RewardKit kills its launch PID: use the pinned ELF directly to close pipes.
RUN set -eux; \
    vendor="/usr/local/lib/node_modules/@openai/codex/node_modules/@openai/codex-linux-x64/vendor/x86_64-unknown-linux-musl"; \
    test -x "$vendor/bin/codex"; \
    ln -sf "$vendor/bin/codex" "/root/.cache/harbor-rewardkit/codex/${REWARDKIT_CODEX_VERSION}/bin/codex"; \
    "$vendor/bin/codex" --version | grep -Fx "codex-cli ${REWARDKIT_CODEX_VERSION}"
# Preserve bundled helpers while bypassing the Node launcher for judge cleanup.
ENV PATH="/usr/local/lib/node_modules/@openai/codex/node_modules/@openai/codex-linux-x64/vendor/x86_64-unknown-linux-musl/bin:/usr/local/lib/node_modules/@openai/codex/node_modules/@openai/codex-linux-x64/vendor/x86_64-unknown-linux-musl/codex-path:${PATH}"
RUN useradd --create-home --uid 10001 --user-group submission \
    && mkdir -p /app /task/corpus /task/models /task/runtime /logs/verifier /audit
COPY . /tests/
RUN cp -r /tests/jailbreak_judge /audit/ \
    && chmod -R 0700 /tests /audit
ENV OMP_NUM_THREADS=16 OPENBLAS_NUM_THREADS=16 MKL_NUM_THREADS=16 TOKENIZERS_PARALLELISM=false HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
WORKDIR /app
