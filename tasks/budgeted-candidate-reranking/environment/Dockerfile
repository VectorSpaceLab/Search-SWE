FROM docker.io/hanhainebula/search-swe-base:gpu-cu13.0-py3.12-1.0.0
ENV HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 TOKENIZERS_PARALLELISM=false
ENV OMP_NUM_THREADS=16 OPENBLAS_NUM_THREADS=16 MKL_NUM_THREADS=16 NUMEXPR_NUM_THREADS=16
RUN /opt/conda/bin/python -m pip install --no-cache-dir --index-url https://pypi.tuna.tsinghua.edu.cn/simple "nvidia-ml-py==13.580.82"
RUN useradd --create-home --uid 10001 --user-group submission \
    && mkdir -p /app /task/data /task/models /task/runtime /task/docs /work \
    && chmod 0700 /task/models

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


COPY runtime/ /task/runtime/
COPY baselines/ /task/baselines/
RUN chmod -R a+rX /task/baselines
RUN find /task/runtime -type d -exec chmod 0555 {} + && find /task/runtime -type f -exec chmod 0444 {} +
WORKDIR /app
