FROM docker.io/hanhainebula/search-swe-base:cpu-py3.12-1.0.0

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

RUN mkdir -p /app/submission /task/public /task/docs /task/tools /logs
COPY exact_search.py baseline_search.py /task/reference/
COPY profile_public.py runtime_limits.py /task/tools/
