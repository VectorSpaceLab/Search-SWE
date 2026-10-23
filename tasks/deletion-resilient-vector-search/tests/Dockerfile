FROM docker.io/hanhainebula/search-swe-base:cpu-py3.12-1.0.0

RUN curl --fail --location --retry 3 --max-time 120 \
      'https://deb.debian.org/debian/pool/main/f/fuse/libfuse2_2.9.9-6+b1_amd64.deb' -o /tmp/libfuse2.deb \
    && curl --fail --location --retry 3 --max-time 120 \
      'https://deb.debian.org/debian/pool/main/e/e2fsprogs/fuse2fs_1.47.0-2+b2_amd64.deb' -o /tmp/fuse2fs.deb \
    && echo 'df32b8f65d819f854e096896890d6ad632b6e520977bb120bb3143b4c66e2fcd  /tmp/libfuse2.deb' | sha256sum -c - \
    && echo '1b3b1e4dad7c409842464871ee61dc978d1c7a19dfa7f42b682fca9b62ccadb4  /tmp/fuse2fs.deb' | sha256sum -c - \
    && dpkg -i /tmp/libfuse2.deb /tmp/fuse2fs.deb \
    && rm /tmp/libfuse2.deb /tmp/fuse2fs.deb

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

RUN useradd --create-home --uid 10001 --user-group submission
RUN /opt/conda/bin/python -c 'import faiss,numpy,psutil,ctypes; assert (faiss.__version__,numpy.__version__,psutil.__version__) == ("1.15.0","2.5.2","7.2.2"); ctypes.CDLL("libseccomp.so.2")'
RUN /opt/conda/bin/python -c 'import matplotlib; assert matplotlib.__version__ == "3.11.1"'

COPY . /tests/

RUN chmod 700 /tests \
    && chmod 700 /tests/test.sh
