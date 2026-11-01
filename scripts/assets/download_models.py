#!/usr/bin/env python3
"""Download only the fixed input models required by selected tasks."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.assets.download_assets import main


if __name__ == "__main__":
    sys.exit(main(default_kind="models"))
