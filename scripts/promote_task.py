#!/usr/bin/env python3
"""Compatibility entrypoint for the portable two-phase promotion helper."""
try:
    from _maintainer_skill import REPO, helpers
except ModuleNotFoundError:
    from scripts._maintainer_skill import REPO, helpers

promote = helpers.promote


def main():
    return helpers.promotion_main(REPO)


if __name__ == "__main__":
    raise SystemExit(main())
