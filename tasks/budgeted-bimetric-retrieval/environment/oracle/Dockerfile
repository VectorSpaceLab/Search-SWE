FROM docker.io/hanhainebula/search-swe-base:cpu-py3.12-1.0.0
COPY . /oracle/
ENV OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1
CMD ["/opt/conda/bin/python", "/oracle/server.py"]
