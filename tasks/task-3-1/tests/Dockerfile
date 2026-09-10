FROM search-swe-base:cpu-py3.12-1.0.0-codex-npm-0.151.0

ENV LITELLM_LOCAL_MODEL_COST_MAP=true

RUN /opt/conda/bin/python -m pip install --no-cache-dir \
    "harbor-rewardkit==0.1.7" \
    && test -x /opt/conda/bin/rewardkit

RUN useradd --create-home --uid 10001 --shell /bin/bash submission

COPY . /tests/
COPY starter/ /baseline-starter/

RUN mkdir -p /task/data /task/docs \
    && chown -R root:root /tests /baseline-starter \
    && chmod 700 /tests /tests/data \
    && chmod 700 /tests/test.sh \
    && chmod 555 /baseline-starter /baseline-starter/src \
    && chmod 555 /baseline-starter/build.sh /baseline-starter/run.sh \
    && chmod 444 /baseline-starter/src/sparse_retrieval.py
