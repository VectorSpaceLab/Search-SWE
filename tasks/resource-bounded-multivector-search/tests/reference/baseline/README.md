# Optional high-recall baseline

`run.sh` serves the persistent JSONL interface directly using the fixed read-only
`/task/data/public/baseline/` assets. You may call it from `/app/run.sh`, import or
modify the source, or replace the system. The public checker accepts it directly:

```bash
python /task/tools/check_submission.py --command /task/tools/baseline/run.sh --queries 5000
```

The token index uses OPQ32, 8,192 IVF cells, and 32 product-quantizer components
with 8 bits each. Search uses five cells and 736 token hits per query token.
A native bitset collector deduplicates token hits into corpus-row order.
Unique candidate documents are reranked with their original FP32 vectors using
`kernel.cpp`; returned ties use corpus order. `serve.py` loads metadata explicitly
and overrides the serialized index's search setting. No test queries or labels
were used to build this index. Its frozen bytes and token mapping are covered by
`assets.json`; the ready index is supplied, so rebuilding is optional.

To rebuild from the public corpus within development time:

```bash
python /task/tools/baseline/build_index.py --index /app/index
```

The builder records elapsed build time and parameters; rebuilding can produce
different training bytes. A custom server can use its load request's `index`
path instead of the supplied launcher's fixed public index override.
Compile the kernel when copying the source to a custom location:

```bash
g++ -O3 -mavx2 -mfma -fopenmp -shared -fPIC kernel.cpp collect.cpp -o libcandidate.so
```

The pinned baseline is measured in every verification before submitted code starts.
Matching its same-run time earns zero. Frozen B/U times define the relative speed
target; same-run normalization corrects machine-speed variation. The baseline
time is not an additional submission time limit.
Mean Recall@100 must reach 0.99 before faster complete-workload timing earns
points. See the instruction and `/task/tools/runtime_limits.py` for the scoring formula and
fixed timing parameters. The exhaustive tools remain available separately to
define original-vector MaxSim semantics.
