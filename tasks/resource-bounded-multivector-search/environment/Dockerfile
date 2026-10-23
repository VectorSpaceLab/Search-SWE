FROM docker.io/hanhainebula/search-swe-base:cpu-py3.12-1.0.0

ARG SEARCH_SWE_CODEX_VERSION=0.157.1
ARG SEARCH_SWE_CLAUDE_CODE_VERSION=2.1.283
ARG SEARCH_SWE_PI_VERSION=0.87.1
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

COPY tools /task/tools
COPY docs /task/docs
COPY budget_evidence.py /task/budget_evidence.py
RUN g++ -O3 -mavx2 -mfma -fopenmp -shared -fPIC /task/tools/maxsim.cpp -o /task/tools/libmaxsim.so
RUN g++ -O3 -mavx2 -mfma -fopenmp -shared -fPIC /task/tools/baseline/kernel.cpp /task/tools/baseline/collect.cpp -o /task/tools/baseline/libcandidate.so
RUN chmod -R a+rX /task/tools /task/docs && chmod 755 /task/tools/*.py && mkdir -p /app
RUN /opt/conda/bin/python -c 'import faiss,numpy,psutil,orjson; assert (faiss.__version__,numpy.__version__,psutil.__version__) == ("1.15.0","2.5.2","7.2.2")'

RUN useradd --create-home --uid 10001 --user-group submission
ENV HOME=/home/submission
CMD ["sh", "-c", "sleep infinity"]
