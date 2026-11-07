FROM docker.io/hanhainebula/search-swe-base:cpu-py3.12-1.0.0

COPY starter/ /app/starter/
COPY build.sh run.sh /app/
RUN chmod +x /app/build.sh /app/run.sh /app/starter/build.sh /app/starter/run.sh
