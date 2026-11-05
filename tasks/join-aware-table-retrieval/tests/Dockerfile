FROM docker.io/hanhainebula/search-swe-base:cpu-py3.12-1.0.0

ENV LITELLM_LOCAL_MODEL_COST_MAP=true
RUN /opt/conda/bin/python -m pip install --no-cache-dir \
    --index-url https://pypi.tuna.tsinghua.edu.cn/simple \
    "harbor-rewardkit==0.2.0" "litellm==1.97.0"
ARG REWARDKIT_CODEX_VERSION=0.164.0
ARG SEARCH_SWE_NPM_REGISTRY=https://registry.npmmirror.com
RUN npm install --global --registry="$SEARCH_SWE_NPM_REGISTRY" \
      "@openai/codex@${REWARDKIT_CODEX_VERSION}" \
    && mkdir -p "/root/.cache/harbor-rewardkit/codex/${REWARDKIT_CODEX_VERSION}/bin" \
    && ln -s "$(command -v codex)" \
      "/root/.cache/harbor-rewardkit/codex/${REWARDKIT_CODEX_VERSION}/bin/codex" \
    && codex --version | grep -Fx "codex-cli ${REWARDKIT_CODEX_VERSION}"

RUN useradd --create-home --uid 10001 --user-group submission

RUN mkdir -p /work /task/data /logs/verifier /audit \
    && chmod 755 /work /logs \
    && chmod 700 /logs/verifier

COPY launch.py /runner/launch.py
RUN chmod 555 /runner && chmod 444 /runner/launch.py

COPY . /tests/

RUN cp -r /tests/jailbreak_judge /audit/ \
    && chmod -R 700 /tests /audit \
    && chmod 700 /tests/test.sh
