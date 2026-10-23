FROM docker.io/hanhainebula/search-swe-base:gpu-cu13.0-py3.12-1.0.0
ARG SEARCH_SWE_CODEX_VERSION=0.157.1
ARG SEARCH_SWE_CLAUDE_CODE_VERSION=2.1.283
ARG SEARCH_SWE_PI_VERSION=0.87.1
RUN npm install --global --ignore-scripts --registry=https://registry.npmmirror.com "@openai/codex@${SEARCH_SWE_CODEX_VERSION}" "@earendil-works/pi-coding-agent@${SEARCH_SWE_PI_VERSION}" && npm install --global --registry=https://registry.npmmirror.com "@anthropic-ai/claude-code@${SEARCH_SWE_CLAUDE_CODE_VERSION}" && codex --version | grep -Fx "codex-cli ${SEARCH_SWE_CODEX_VERSION}"
RUN test "$(pi --version)" = "${SEARCH_SWE_PI_VERSION}" && test "$(claude --version)" = "${SEARCH_SWE_CLAUDE_CODE_VERSION} (Claude Code)"
RUN claude --help | grep -F "(low, medium, high, xhigh, max)" >/dev/null
RUN /opt/conda/bin/python -m pip install --no-cache-dir --index-url https://pypi.tuna.tsinghua.edu.cn/simple "nvidia-ml-py==13.580.82"
RUN useradd --create-home --uid 10001 --user-group submission && mkdir -p /app /task/runtime /task/docs /task/baselines /opt/harbor
COPY runtime/ /task/runtime/
COPY docs/ /task/docs/
COPY baselines/ /task/baselines/
ENV SEARCH_SWE_AGENT_CONTAINER=1 OMP_NUM_THREADS=16 OPENBLAS_NUM_THREADS=16 MKL_NUM_THREADS=16 PYTHONDONTWRITEBYTECODE=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 XDG_CACHE_HOME=/app/.cache
WORKDIR /app
