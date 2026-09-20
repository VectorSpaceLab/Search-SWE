FROM docker.io/hanhainebula/search-swe-base:cpu-py3.12-1.0.0

ARG PIP_FIND_LINKS
ARG PIP_NO_INDEX
ARG PIP_TRUSTED_HOST

COPY requirements.txt /tmp/verifier-requirements.txt
RUN /opt/conda/bin/python -m pip install --no-cache-dir -r /tmp/verifier-requirements.txt \
    && npm install --global @openai/codex@0.151.0 \
    && useradd --create-home --uid 10001 --user-group submission
COPY . /tests/
RUN chmod 700 /tests && chmod 700 /tests/test.sh
WORKDIR /app
