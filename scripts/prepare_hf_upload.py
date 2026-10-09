#!/usr/bin/env python3
"""Compatibility entrypoint for the portable offline HF staging helper."""
try:
    from _maintainer_skill import helpers
except ModuleNotFoundError:
    from scripts._maintainer_skill import helpers

prepare = helpers.prepare


def main():
    return helpers.upload_main(legacy=True)


if __name__ == "__main__":
    raise SystemExit(main())
