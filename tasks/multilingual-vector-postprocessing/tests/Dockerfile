FROM docker.io/hanhainebula/search-swe-base:gpu-cu13.0-py3.12-1.0.0
ENV LITELLM_LOCAL_MODEL_COST_MAP=true
RUN /opt/conda/bin/python -m pip install --no-cache-dir --index-url https://pypi.tuna.tsinghua.edu.cn/simple "harbor-rewardkit==0.2.0" "litellm==1.97.0" "nvidia-ml-py==13.580.82"
ARG REWARDKIT_CODEX_VERSION=0.164.0
RUN npm install --global --registry=https://registry.npmmirror.com "@openai/codex@${REWARDKIT_CODEX_VERSION}" && mkdir -p "/root/.cache/harbor-rewardkit/codex/${REWARDKIT_CODEX_VERSION}/bin" && ln -sf "$(command -v codex)" "/root/.cache/harbor-rewardkit/codex/${REWARDKIT_CODEX_VERSION}/bin/codex" && codex --version | grep -Fx "codex-cli ${REWARDKIT_CODEX_VERSION}"
RUN useradd --create-home --uid 10001 --user-group submission && mkdir -p /app /private /task/runtime /logs/verifier /audit
COPY . /tests/
RUN cp -r /tests/runtime/. /task/runtime/ && cp -r /tests/jailbreak_judge /audit/ && chmod -R 0700 /tests /audit /private && chmod -R a+rX /task/runtime
ENV OMP_NUM_THREADS=16 OPENBLAS_NUM_THREADS=16 MKL_NUM_THREADS=16 PYTHONDONTWRITEBYTECODE=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 SEARCH_SWE_VERIFIER_SANDBOX=1 XDG_CACHE_HOME=/root/.cache
WORKDIR /app
