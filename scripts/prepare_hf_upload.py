#!/usr/bin/env python3
"""Repository entrypoint for the portable offline HF staging helper."""
try:
    from _maintainer_skill import helpers
except ModuleNotFoundError:
    from scripts._maintainer_skill import helpers

prepare = helpers.prepare


def main():
    return helpers.upload_main(repository_cli=True)


if __name__ == "__main__":
    raise SystemExit(main())
