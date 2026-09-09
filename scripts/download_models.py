#!/usr/bin/env python3
"""Download only the fixed input models required by selected tasks."""

import sys

from download_assets import main


if __name__ == "__main__":
    sys.exit(main(default_kind="models"))
