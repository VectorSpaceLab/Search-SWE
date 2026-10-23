#!/bin/sh
set -eu
export OMP_NUM_THREADS=8 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
export OMP_WAIT_POLICY=PASSIVE KMP_BLOCKTIME=0
exec /opt/conda/bin/python /task/tools/baseline/serve.py --index /task/data/public/baseline
