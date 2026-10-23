FROM docker.io/hanhainebula/search-swe-base:cpu-py3.12-1.0.0

COPY install-rust.sh /tmp/install-rust.sh
RUN sh /tmp/install-rust.sh && rm /tmp/install-rust.sh
ENV PATH="/opt/rust/bin:${PATH}" CARGO_HOME=/opt/cargo
COPY starter/ /app/submission/
RUN cd /app/submission && cargo fetch --locked \
    && cargo build --release --locked --offline \
    && rm -rf target \
    && mkdir -p /task/data /task/docs /logs
WORKDIR /app/submission
ENV CARGO_TARGET_DIR=/app/build
COPY smoke.py /task/smoke.py

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
