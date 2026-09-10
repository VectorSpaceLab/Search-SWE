FROM search-swe-base:cpu-py3.12-1.0.0-codex-npm-0.151.0

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY . /tests/

RUN chown -R root:root /tests \
    && chmod 700 /tests /tests/test.sh /tests/*.py \
    && chmod 700 /tests/data \
    && chmod 600 /tests/data/queries.jsonl /tests/data/qrels_gold.txt \
    && test "$(wc -l < /tests/data/queries.jsonl)" -eq 20 \
    && test "$(wc -l < /tests/data/qrels_gold.txt)" -eq 63 \
    && mkdir -p /app /logs /task/data

CMD ["sleep", "infinity"]
