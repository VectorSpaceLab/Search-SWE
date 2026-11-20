"""Replace Harbor's CLI entry point in an isolated checkout, retaining the real Harbor library."""

from pathlib import Path

import harbor


def cli_module(checkout):
    package = checkout / "harbor"
    cli = package / "cli"
    cli.mkdir(parents=True, exist_ok=True)
    # Preserve the installed package's public API and module search locations.
    installed = Path(harbor.__file__).parent
    (package / "__init__.py").write_text(
        f"__path__.append({str(installed)!r})\n" + (installed / "__init__.py").read_text())
    (cli / "__init__.py").write_text(f"__path__.append({str(installed / 'cli')!r})\n")
    return cli / "main.py"
