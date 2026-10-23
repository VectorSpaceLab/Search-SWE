FROM docker.io/hanhainebula/search-swe-base:gpu-cu13.0-py3.12-1.0.0

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

# Isolate the supplied model's Transformers 4 runtime from the shared image.
RUN /opt/conda/bin/python -m venv --system-site-packages /opt/stella \
    && /opt/stella/bin/python -m pip install --no-cache-dir \
        --index-url https://pypi.tuna.tsinghua.edu.cn/simple \
        --timeout 120 --retries 5 \
        "transformers==4.44.2" "tokenizers==0.19.1" \
        "huggingface-hub==0.36.0" "sentence-transformers==3.0.1" "einops==0.8.1" "peft==0.12.0"

RUN mkdir -p /app /task/data /task/docs /logs
