FROM docker.io/hanhainebula/search-swe-base:gpu-cu13.0-py3.12-1.0.0

# The judge uses the Codex CLI endpoint, not LiteLLM's remote pricing map.
# Keep verifier startup/build deterministic and avoid an unrelated GitHub fetch.
ENV LITELLM_LOCAL_MODEL_COST_MAP=true

RUN /opt/conda/bin/python -m pip install --no-cache-dir \
    --index-url https://pypi.tuna.tsinghua.edu.cn/simple \
    --timeout 120 --retries 10 --resume-retries 10 \
    "harbor-rewardkit==0.2.0" "litellm==1.97.0"

ARG REWARDKIT_CODEX_VERSION=0.147.0
ARG REWARDKIT_CODEX_NPM_REGISTRY=https://registry.npmmirror.com
RUN set -eux; \
    root="/root/.cache/harbor-rewardkit/codex/${REWARDKIT_CODEX_VERSION}"; \
    npm install --global --registry="$REWARDKIT_CODEX_NPM_REGISTRY" \
      "@openai/codex@${REWARDKIT_CODEX_VERSION}"; \
    mkdir -p "$root/bin"; \
    ln -sf "$(command -v codex)" "$root/bin/codex"; \
    "$root/bin/codex" --version | grep -Fx "codex-cli ${REWARDKIT_CODEX_VERSION}"

COPY --chmod=755 test.sh run_evaluation.sh finalize_reward.py /tests/
COPY --chmod=644 grader.py rewardkit_deepseek.py /tests/
COPY --chmod=600 data/queries.jsonl data/ground_truth.jsonl /tests/data/
COPY jailbreak_judge/ /tests/jailbreak_judge/

RUN chmod 700 /tests /tests/data
