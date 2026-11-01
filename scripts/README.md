# Repository tools

Use [`search-swe run`](../docs/evaluation/quickstart.md) to configure and run
evaluations. The CLI calls the checkout tools below for asset preparation and
execution. Contributors and maintainers can also use them directly.

Run the examples from the repository root in the Python environment containing
Search-SWE. Python entry points also accept an absolute script path from another
working directory, or `python -m scripts.<group>.<module>` from the checkout.

## Tool groups

| Directory | Responsibilities | Entry points |
| --- | --- | --- |
| [evaluation/](evaluation/) | Single-task launcher, Harbor adapters, CPU/GPU allocation, storage, harness pins and Pi metadata | `run_task.py`, `run_task.sh`, `update_pi_catalog.mjs` |
| [assets/](assets/) | Download and verify fixed inputs, estimate disk usage, stage HF publication files | `download_assets.py`, `download_models.py`, `prepare_hf_upload.py` |
| [validation/](validation/) | Static task-package and release checks | `check_tasks.py`, `check_release.py` |
| [egress/](egress/) | Runtime network policy, gateway builds and owned-resource recovery | `build_egress_component.py`, `build_egress_gateway.py`, `egress_cleanup.py` |

[`task_paths.py`](task_paths.py) provides shared task discovery and path validation.
Other modules support the entry points; settings and usage are documented in
[host setup](../docs/evaluation/runtime.md), [assets](../docs/evaluation/assets.md)
and [network policy](../docs/evaluation/network.md).

## Common contributor commands

```bash
python scripts/validation/check_tasks.py tasks/example-search
python scripts/validation/check_release.py
python scripts/assets/download_assets.py --task example-search --dry-run
python scripts/evaluation/run_task.py --task example-search \
  --agent codex --openrouter --model openai/gpt-6-luna --dry-run
```

Use each command's `--help` for its options. The [contribution guide](../docs/contributing/tasks.md)
covers task validation and model feedback. HF staging is documented in the
[asset publication workflow](../docs/contributing/tasks.md#asset-contribution-and-publication);
gateway builds and Docker checks are in the [egress guide](../environments/egress/README.md).

## Tests and maintenance

Repository regressions and Docker integration fixtures live in [`tests/`](../tests/).
Task-specific grading and regression tests remain under `tasks/<task-name>/tests/`.
Skill-local tests remain bundled with their skills.

When changing a tool path or import, update its CLI caller, Harbor import strings,
CI, tests, docs and skill references together. Keep the package and checkout's
version contract aligned; checkout tools are provided by the repository, while
`src/search_swe/` supplies the installed CLI.
