#!/usr/bin/env bash
set -euo pipefail
exec /usr/bin/env -i \
    JAVA_HOME=/opt/java/openjdk \
    HOME=/root PATH=/opt/conda/bin:/opt/java/openjdk/bin:/usr/bin:/bin \
    LD_LIBRARY_PATH=/usr/local/nvidia/lib:/usr/local/nvidia/lib64:/opt/conda/lib \
    LANG=C.UTF-8 LC_ALL=C.UTF-8 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
    OMP_NUM_THREADS=8 OPENBLAS_NUM_THREADS=8 PYTHONDONTWRITEBYTECODE=1 \
    /opt/conda/bin/python /tests/evaluate.py
