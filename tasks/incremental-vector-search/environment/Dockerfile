FROM docker.io/hanhainebula/search-swe-base:cpu-py3.12-1.0.0

ENV OMP_NUM_THREADS=16 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1

RUN mkdir -p /app/submission /task/data/corpus /task/docs /task/tools /logs
COPY exact_search.py baseline_search.py /task/reference/
COPY profile_public.py runtime_limits.py /task/tools/
RUN chmod 755 /task/reference /task/tools && chmod 644 /task/reference/*.py /task/tools/*.py

ENTRYPOINT ["/opt/conda/bin/python", "/task/tools/runtime_limits.py"]
CMD ["sleep", "infinity"]
