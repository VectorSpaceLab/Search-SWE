FROM search-swe-base:cpu-py3.12-1.0.0-codex-npm-0.151.0

RUN mkdir -p /app /task/data /task/docs /logs

COPY starter/ /app/starter/
COPY build.sh run.sh /app/
RUN chmod +x /app/build.sh /app/run.sh /app/starter/build.sh /app/starter/run.sh
