# Sources and Preparation

## Sources and reproduction

[SWE-Explore paper](https://arxiv.org/abs/2606.07297), [SWE-Explore dataset](https://huggingface.co/datasets/SWE-Explore-Bench/SWE-Explore-Bench), and [SWE-Explore implementation](https://github.com/Qiushao-E/SWE-Explore-Bench).

Dataset revision: `bdb0ae45d7c337d9e1dc3ebfe2a0af6bc7c1fbd9`; release SHA-256: `dc4f114ececd0bfb987361c26ae5e2440456e2cccb36adfccb09ea5385aec202`. SWE-Explore implementation revision: `5602f031f2d9562d0a805f83402b536e831a5a11`. Issues and base commits were joined by exact IDs to pinned SWE-bench Verified, Multilingual and Pro v1 releases. Attribution and per-snapshot origins are in [LICENSE.data.md](LICENSE.data.md).

The authoring directory is `task_development/code-bug-localization`, adjacent to this Search-SWE checkout. It contains source downloads, the frozen selection, per-query baseline traces, review notes, export scripts, source hashes and author-only runtime fixtures. None is mounted into the solver environment. Reproduce the export with `python task_development/code-bug-localization/package_task.py` from the parent workspace; its input is the already frozen `selection/`.

Run `python scripts/assets/download_assets.py --task code-context-retrieval --verify-only` from this checkout to verify local asset hashes, and `python -m unittest discover -s tasks/code-context-retrieval/tests -p test_contract.py` for scoring regression checks. [VALIDATION.md](VALIDATION.md) records actual runtime checks and remaining validation layers.

Public inputs are published and pinned to immutable revisions in `assets.json`, with exact sizes and SHA-256 hashes. Unchanged model pins are retained. See [RUN_RESULTS.md](RUN_RESULTS.md) for the current run evidence and publication status. Existing source terms and attribution remain applicable.
