FROM docker.io/hanhainebula/search-swe-base:gpu-cu13.0-py3.12-1.0.0

RUN /opt/conda/bin/python -m pip install --no-cache-dir --index-url https://pypi.tuna.tsinghua.edu.cn/simple \
    "rdkit==2024.3.5" "duckdb==1.3.2" "tensorboard==2.20.0" "lightgbm==4.6.0"
RUN /opt/conda/bin/python -m pip install --no-cache-dir --index-url https://pypi.tuna.tsinghua.edu.cn/simple "nvidia-ml-py==12.560.30"
ARG SEARCH_SWE_CODEX_VERSION=0.164.0
ARG SEARCH_SWE_CLAUDE_CODE_VERSION=2.1.309
ARG SEARCH_SWE_PI_VERSION=1.4.0
RUN --mount=type=cache,id=constrained-molecular-npm,target=/root/.npm npm install --global --ignore-scripts --no-audit --no-fund --prefer-offline \
        --registry=https://registry.npmjs.org \
        "@openai/codex@${SEARCH_SWE_CODEX_VERSION}" \
        "@earendil-works/pi-coding-agent@${SEARCH_SWE_PI_VERSION}" \
        "@openai/codex-linux-x64@npm:@openai/codex@${SEARCH_SWE_CODEX_VERSION}-linux-x64" \
    && npm install --global --no-audit --no-fund --prefer-offline \
        --registry=https://registry.npmjs.org \
        "@anthropic-ai/claude-code@${SEARCH_SWE_CLAUDE_CODE_VERSION}" \
    && codex --version | grep -Fx "codex-cli ${SEARCH_SWE_CODEX_VERSION}" \
    && test "$(pi --version)" = "${SEARCH_SWE_PI_VERSION}" \
    && test "$(claude --version)" = "${SEARCH_SWE_CLAUDE_CODE_VERSION} (Claude Code)"
RUN claude --help | grep -F "(low, medium, high, xhigh, max)" >/dev/null
COPY vendor/ /opt/apex-sources/
RUN mkdir /opt/apex-sources/apex_topk/cccl \
    && tar -xzf /opt/apex-sources/cccl-8dce9c1-headers.tar.gz -C /opt/apex-sources/apex_topk/cccl \
    && cd /opt/apex-sources/apex_topk \
    && MAX_JOBS=2 /opt/conda/bin/python -m pip install --no-build-isolation --no-deps . \
    && cd /opt/apex-sources/apex \
    && /opt/conda/bin/python -m pip install --no-deps . \
    && rm -rf /opt/apex-sources/apex_topk/build
RUN /opt/conda/bin/python -c "from apex_topk import topk; from apex.nn.apex import APEXFactorizedCSL"
RUN mkdir -p /app/submission /task/library /task/models /task/train /task/dev /task/docs /task/runtime /logs

COPY runtime/ /task/runtime/
RUN chmod -R a+rX /task/runtime
COPY docs/ /task/docs/
RUN chmod -R a+rX /task/docs
