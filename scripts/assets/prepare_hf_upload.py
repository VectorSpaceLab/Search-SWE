#!/usr/bin/env python3
"""Repository entrypoint for the portable offline HF staging helper."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.assets._maintainer_skill import helpers

# Apply the repository's asset policy only to its publication entrypoint.
# The portable skill and its loader retain their independent behavior.
if (Path(__file__).resolve().parent / 'download_assets.py').is_file():
    from scripts.assets.download_assets import read_manifest
    helpers.read_manifest = read_manifest

prepare = helpers.prepare


def main():
    return helpers.upload_main(repository_cli=True)


if __name__ == "__main__":
    raise SystemExit(main())
