FROM docker.io/hanhainebula/search-swe-base:gpu-cu13.0-py3.12-1.0.0

ENV HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1

RUN mkdir -p /app /task/data /task/docs /logs

COPY starter/ /app/starter/
RUN chmod +x /app/starter/train.sh
