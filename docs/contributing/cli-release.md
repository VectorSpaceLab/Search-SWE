# Publishing the CLI package

[Documentation index](../README.md)

This guide is for maintainers releasing `search-swe` to PyPI.

Choose an unused package version and set it in both `pyproject.toml` and
`src/search_swe/__init__.py`. Task versions are managed independently. The PyPI
project description comes from `docs/evaluation/cli.md`, as configured by the `readme` field
in `pyproject.toml`; review that user-facing guide before building.

CLI 0.2.x requires a 0.2.x checkout. Publish compatible checkout changes alongside
the package; a patch release must preserve that series' CLI/backend contract.

From the repository root, build into a fresh directory and validate the artifacts:

```bash
python -m pip install build twine
search_swe_dist=$(mktemp -d)
python -m build --outdir "$search_swe_dist"
python -m twine check --strict "$search_swe_dist"/*
```

Inspect the wheel and sdist: they should contain the CLI, package metadata,
license and user documentation. Credentials, task datasets, trajectories and job
outputs stay outside the distributions.

After validation, upload those artifacts:

```bash
python -m twine upload --repository-url https://upload.pypi.org/legacy/ \
  --username __token__ "$search_swe_dist"/*
```

Enter the complete `pypi-...` API token at the hidden credential prompt. Published
release descriptions are updated by publishing a new version, including when
only documentation changes. See the [PyPI documentation](https://dev.pypi.org/application/#historical-context-deprecations).
