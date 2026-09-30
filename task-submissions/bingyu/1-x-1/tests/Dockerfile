FROM docker.io/hanhainebula/search-swe-base:cpu-py3.12-1.0.0

ENV LITELLM_LOCAL_MODEL_COST_MAP=true

RUN /opt/conda/bin/python -m pip install --no-cache-dir \
    --index-url https://pypi.tuna.tsinghua.edu.cn/simple \
    --timeout 120 --retries 3 "harbor-rewardkit==0.1.7"

ARG REWARDKIT_CODEX_VERSION=0.151.0
RUN npm install --global --registry=https://registry.npmmirror.com \
      "@openai/codex@${REWARDKIT_CODEX_VERSION}" \
    && codex --version | grep -Fx "codex-cli ${REWARDKIT_CODEX_VERSION}"

RUN useradd --create-home --uid 10001 --user-group submission
COPY . /tests/
RUN mkdir -p /app /task/data/corpus /task/docs \
    && chown -R root:root /tests \
    && chmod 700 /tests \
    && chmod 700 /tests/test.sh
RUN /opt/conda/bin/python -c "import ctypes.util; assert ctypes.util.find_library('seccomp')"
WORKDIR /app
