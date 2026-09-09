FROM search-swe-base:cpu-py3.12-1.0.0-codex-npm-0.151.0

RUN useradd --create-home --uid 10001 --user-group submission

COPY . /tests/

RUN mkdir -p /task/data /task/models /task/docs \
    && chown -R root:root /tests \
    && chmod 700 /tests \
    && chmod 700 /tests/test.sh
