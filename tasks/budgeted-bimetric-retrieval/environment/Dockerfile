FROM docker.io/hanhainebula/search-swe-base:cpu-py3.12-1.0.0

COPY tools /task/tools
COPY baseline /task/baseline
RUN useradd --create-home --uid 10001 --user-group submission \
    && mkdir -p /app /task/public /task/docs /run/oracle \
    && chmod -R a+rX /task/tools /task/baseline \
    && chmod 755 /task/baseline/search.sh
RUN /opt/conda/bin/python -c 'import faiss,numpy,pyarrow,psutil,sklearn,Stemmer,threadpoolctl; import ctypes; ctypes.CDLL("libseccomp.so.2")'
ENV HOME=/home/submission
CMD ["sh", "-c", "sleep infinity"]
