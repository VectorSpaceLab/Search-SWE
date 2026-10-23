FROM docker.io/hanhainebula/search-swe-base:gpu-cu13.0-py3.12-1.0.0

RUN /opt/conda/bin/python -m pip install --no-cache-dir --index-url https://pypi.tuna.tsinghua.edu.cn/simple \
    "rdkit==2024.3.5" "duckdb==1.3.2" "tensorboard==2.20.0" "lightgbm==4.6.0"
RUN /opt/conda/bin/python -m pip install --no-cache-dir --index-url https://pypi.tuna.tsinghua.edu.cn/simple "nvidia-ml-py==12.560.30"
COPY vendor/ /opt/apex-sources/
RUN mkdir /opt/apex-sources/apex_topk/cccl \
    && tar -xzf /opt/apex-sources/cccl-8dce9c1-headers.tar.gz -C /opt/apex-sources/apex_topk/cccl \
    && cd /opt/apex-sources/apex_topk \
    && MAX_JOBS=2 /opt/conda/bin/python -m pip install --no-build-isolation --no-deps . \
    && cd /opt/apex-sources/apex \
    && /opt/conda/bin/python -m pip install --no-deps . \
    && rm -rf /opt/apex-sources/apex_topk/build
RUN /opt/conda/bin/python -c "from apex_topk import topk; from apex.nn.apex import APEXFactorizedCSL"
RUN mkdir -p /app /task/library /task/models /task/train /task/dev /task/docs /task/runtime /logs

RUN useradd --create-home --uid 10001 --user-group submission
COPY . /tests/
RUN chmod 0700 /tests

COPY runtime/ /task/runtime/
RUN chmod -R a+rX /task/runtime
COPY docs/ /task/docs/
RUN chmod -R a+rX /task/docs

ENV LITELLM_LOCAL_MODEL_COST_MAP=true

RUN /opt/conda/bin/python -m pip install --no-cache-dir \
    --index-url https://pypi.tuna.tsinghua.edu.cn/simple \
    --timeout 120 --retries 10 --resume-retries 10 \
    "harbor-rewardkit==0.2.0" \
    "litellm==1.97.0"

ARG REWARDKIT_CODEX_VERSION=0.164.0
ARG REWARDKIT_CODEX_NPM_REGISTRY=https://registry.npmmirror.com
RUN set -eux; \
    root="/root/.cache/harbor-rewardkit/codex/${REWARDKIT_CODEX_VERSION}"; \
    npm install --global --registry="$REWARDKIT_CODEX_NPM_REGISTRY" \
      "@openai/codex@${REWARDKIT_CODEX_VERSION}"; \
    mkdir -p "$root/bin"; \
    ln -sf "$(command -v codex)" "$root/bin/codex"; \
    "$root/bin/codex" --version | grep -Fx "codex-cli ${REWARDKIT_CODEX_VERSION}"

COPY integrity_judge/ /audit/integrity_judge/
RUN chmod -R go-rwx /audit
