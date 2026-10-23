FROM docker.io/hanhainebula/search-swe-base:gpu-cu13.0-py3.12-1.0.0

RUN /opt/conda/bin/python -m pip install --no-cache-dir \
    --index-url https://pypi.tuna.tsinghua.edu.cn/simple \
    "bitsandbytes==0.50.2"

# Optional fixed-weight inference kernels; preserve the shared image's torch stack.
RUN /opt/conda/bin/python -m pip install --no-cache-dir --no-deps \
    --index-url https://pypi.tuna.tsinghua.edu.cn/simple \
    "gemlite==0.6.0.post2" "hqq==0.2.8.post1" "termcolor==3.3.0"

ARG SEARCH_SWE_CODEX_VERSION=0.164.0
ARG SEARCH_SWE_CLAUDE_CODE_VERSION=2.1.309
ARG SEARCH_SWE_PI_VERSION=1.4.0
RUN npm install --global --ignore-scripts \
    --registry=https://registry.npmmirror.com \
    "@openai/codex@${SEARCH_SWE_CODEX_VERSION}" \
    "@earendil-works/pi-coding-agent@${SEARCH_SWE_PI_VERSION}" \
    && npm install --global \
        --registry=https://registry.npmmirror.com \
        "@anthropic-ai/claude-code@${SEARCH_SWE_CLAUDE_CODE_VERSION}" \
    && codex --version | grep -Fx "codex-cli ${SEARCH_SWE_CODEX_VERSION}" \
    && test "$(pi --version)" = "${SEARCH_SWE_PI_VERSION}" \
    && test "$(claude --version)" = "${SEARCH_SWE_CLAUDE_CODE_VERSION} (Claude Code)"
RUN claude --help | grep -F "(low, medium, high, xhigh, max)" >/dev/null

ENV HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 TOKENIZERS_PARALLELISM=false
RUN useradd --create-home --uid 10001 --user-group submission
COPY initial_submission/ /app/submission/
RUN chmod 0755 /app/submission /app/submission/prepare.sh /app/submission/run.sh \
    && chmod 0644 /app/submission/submission.json
WORKDIR /app
