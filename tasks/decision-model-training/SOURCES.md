# Sources and Preparation

## Sources and preparation

- [OpenJev training mixture](https://huggingface.co/datasets/s1lv3rj1nx/openjev-mixture/tree/e540d97fc37e92b493ceeb536bdb7a01e366bdc3): 323,466 original rows.
- [OpenJev held-out suite](https://huggingface.co/datasets/s1lv3rj1nx/openjev-heldout/tree/fc5fe530405de8de02e983adbc5b10795618979c): AG News, Banking77, Civil Comments toxicity, CLINC OOS, HelpSteer helpfulness, MASSIVE intent, SST5.
- [Qwen3-0.6B](https://huggingface.co/Qwen/Qwen3-0.6B/tree/c1899de289a04d12100db370d81485cdf75e47ca): exact files verified against the user-supplied local model; Apache-2.0.
- [OpenJev implementation](https://github.com/S1LV3RJ1NX/openjev/tree/91847b4c678f7d9330d8f3475e24c72c7fef73c2): author-side format and contamination checks; not provided as a solution.

Sample without replacement within every source task configuration, seed
20261014. Proportional largest-remainder allocation yields exactly 80,000 rows,
with 8–742 examples per configuration. Before sampling, exclude two training
rows whose normalized state occurs in the hidden suite. The original 4,200
hidden states, questions, option descriptions/order and typed labels are
preserved. Flatten per-example option overrides into each example's question
schema. Neither new labels nor synthetic questions are generated. The upstream
alias guard and normalized-state overlap check pass. No separate public
validation split or baseline implementation is supplied.

OpenJev's assembly is Apache-2.0; constituent datasets retain their own terms.
Its held-out card explicitly flags unclear redistribution rights for AG News
and SST5. The training mixture also does not supply a complete license audit of
all underlying datasets. This package makes no claim that every row is cleared for republication.
Unresolved constituent terms remain recorded for maintainer review.

## Bundled model documentation

`models/Qwen3-0.6B/README.md` is adapted from `Qwen/Qwen3-0.6B`, revision `c1899de289a04d12100db370d81485cdf75e47ca`, file `README.md`. The bundled card retains the model description, original attribution, Apache-2.0 license metadata and citation. The complete model license is provided at `models/Qwen3-0.6B/LICENSE`. The task restores the bundled card using the size and SHA-256 in `assets.json`.
