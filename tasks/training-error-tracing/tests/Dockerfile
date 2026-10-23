FROM docker.io/hanhainebula/search-swe-base:gpu-cu13.0-py3.12-1.0.0

RUN /opt/conda/bin/python -m pip install --no-cache-dir \
    --index-url https://pypi.tuna.tsinghua.edu.cn/simple \
    "bitsandbytes==0.50.2"

# Optional fixed-weight inference kernels; preserve the shared image's torch stack.
RUN /opt/conda/bin/python -m pip install --no-cache-dir --no-deps \
    --index-url https://pypi.tuna.tsinghua.edu.cn/simple \
    "gemlite==0.6.0.post2" "hqq==0.2.8.post1" "termcolor==3.3.0"

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

RUN useradd --create-home --uid 10001 --user-group submission
COPY . /tests/
COPY control/ /control/
RUN chmod 0755 /control /control/prepare.sh /control/run.sh \
    && chmod 0644 /control/submission.json
COPY jailbreak_judge/ /audit/jailbreak_judge/
RUN mkdir -p /work \
    && chmod 0755 /work \
    && chmod 0700 /tests /audit \
    && chmod 0700 /tests/test.sh \
    && find /tests /audit -type d -exec chmod 0700 {} + \
    && find /tests /audit -type f -exec chmod 0600 {} + \
    && chmod 0700 /tests/test.sh
WORKDIR /app
