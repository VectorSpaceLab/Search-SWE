FROM docker.io/hanhainebula/search-swe-base:cpu-py3.12-1.0.0
RUN useradd --create-home --uid 10001 --user-group submission
RUN mkdir -p /task/private && chmod 700 /task/private
RUN /opt/conda/bin/python -c 'import faiss,numpy,pyarrow,psutil; import ctypes; ctypes.CDLL("libseccomp.so.2")'
COPY *.py test.sh /tests/
COPY data/queries.f32 data/queries.jsonl data/qrels.tsv /task/private/data/
RUN chmod 700 /tests /tests/test.sh /task/private/data \
    && chmod 600 /task/private/data/*
