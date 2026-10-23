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

COPY starter/ /app/

RUN test -x /app/build.sh \
    && test -x /app/run.sh \
    && python3 -m py_compile /app/src/sparse_retrieval.py

# Login shells reset PATH to /usr/local/bin; keep all standard Python entry
# points on the provided Conda runtime, including NumPy and the verifier tools.
ENV OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
    NUMEXPR_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 BLIS_NUM_THREADS=1
RUN ln -sf /opt/conda/bin/python /usr/local/bin/python \
    && ln -sf /opt/conda/bin/python3 /usr/local/bin/python3 \
    && ln -sf /opt/conda/bin/python3.12 /usr/local/bin/python3.12 \
    && bash -lc 'python -c "import numpy; import sys; assert sys.prefix == \"/opt/conda\""' \
    && bash -lc 'python3 -c "import numpy; import sys; assert sys.prefix == \"/opt/conda\""'
