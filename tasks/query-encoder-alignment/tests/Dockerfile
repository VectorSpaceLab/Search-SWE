FROM docker.io/hanhainebula/search-swe-base:gpu-cu13.0-py3.12-1.0.0

# The judge uses the Codex CLI endpoint, not LiteLLM's remote pricing map.
# Keep verifier startup/build deterministic and avoid an unrelated GitHub fetch.
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

RUN useradd --create-home --uid 10001 --shell /bin/bash submission

# One source layer avoids repeated snapshots of the large shared GPU image.
COPY . /tests/
RUN chmod 755 /tests/test.sh /tests/run_evaluation.sh /tests/finalize_reward.py \
        /tests/starter/run.sh /tests/quality_baseline/run.sh \
    && mkdir -p /audit \
    && cp -a /tests/jailbreak_judge /audit/ \
    && chmod 600 /tests/data/queries.jsonl /tests/data/ground_truth.jsonl \
    && chmod 700 /tests /tests/data /audit
