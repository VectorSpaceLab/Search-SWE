FROM docker.io/hanhainebula/search-swe-base:cpu-py3.12-1.0.0

RUN useradd --create-home --uid 10001 --user-group submission
COPY docs /task/docs
COPY tools /task/tools
COPY budget_evidence.py /task/budget_evidence.py
RUN chmod -R a+rX /task && mkdir -p /app
ENV HOME=/home/submission
CMD ["sh", "-c", "sleep infinity"]
