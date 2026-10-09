FROM docker.io/hanhainebula/search-swe-base:cpu-py3.12-1.0.0

COPY . /tests/

RUN chmod 700 /tests /tests/test.sh /tests/*.py \
    && chmod 700 /tests/data \
    && chmod 600 /tests/data/queries.jsonl /tests/data/qrels_gold.txt \
    && test "$(wc -l < /tests/data/queries.jsonl)" -eq 20 \
    && test "$(wc -l < /tests/data/qrels_gold.txt)" -eq 63
