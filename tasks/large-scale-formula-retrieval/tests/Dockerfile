FROM docker.io/hanhainebula/search-swe-base:cpu-py3.12-1.0.0
RUN useradd --create-home --uid 10001 --user-group submission
RUN useradd --create-home --uid 10002 --user-group audit \
    && usermod --append --groups submission audit
COPY . /tests/
COPY build_driver.py /task/tools/build_driver.py
RUN chmod 700 /tests /tests/test.sh && chmod -R a+rX /task/tools

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

COPY jailbreak_judge/ /audit/jailbreak_judge/
RUN chmod -R go-rwx /audit
RUN install -d -m 0755 /opt/audit \
    && install -m 0755 /tests/rewardkit_deepseek.py /opt/audit/runner.py \
    && install -m 0755 /tests/readonly_audit.py /opt/audit/readonly_audit.py \
    && install -m 0644 /tests/landlock_audit.py /opt/audit/landlock_audit.py \
    && install -d -o audit -g audit -m 0700 /home/audit/.cache/harbor-rewardkit/codex/0.164.0/bin \
    && ln -s /usr/local/bin/codex /home/audit/.cache/harbor-rewardkit/codex/0.164.0/bin/codex
