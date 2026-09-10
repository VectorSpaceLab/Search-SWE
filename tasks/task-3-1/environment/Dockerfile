FROM search-swe-base:cpu-py3.12-1.0.0-codex-npm-0.151.0

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt /tmp/requirements.txt
RUN if grep -q '[^[:space:]]' /tmp/requirements.txt; then \
        python -m pip install --no-cache-dir -r /tmp/requirements.txt; \
    fi \
    && rm -f /tmp/requirements.txt

COPY starter/ /app/

RUN test -x /app/build.sh \
    && test -x /app/run.sh \
    && python3 -m py_compile /app/src/sparse_retrieval.py \
    && mkdir -p /app /logs /cache/huggingface \
    && (id -u submission >/dev/null 2>&1 || useradd --create-home --uid 10001 submission)

CMD ["sleep", "infinity"]
