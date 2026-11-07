FROM docker.io/hanhainebula/search-swe-base:cpu-py3.12-1.0.0

COPY query_cpu.c /usr/local/src/search-swe-query-cpu.c
RUN cc -O2 -Wall -Wextra -Werror /usr/local/src/search-swe-query-cpu.c -o /usr/local/bin/search-swe-query-cpu \
    && chmod 0755 /usr/local/bin/search-swe-query-cpu
