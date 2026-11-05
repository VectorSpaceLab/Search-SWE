"""Load the portable skill's single-source offline helpers for the repository CLI."""
import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
path = REPO / ".agents/skills/maintain-searchswe-task/scripts/maintainer_helpers.py"
spec = importlib.util.spec_from_file_location("searchswe_maintainer_helpers", path)
helpers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helpers)

# Repository publication uses the same asset paths as the repository downloader.
# Keep the independently distributable skill and its own path policy unchanged.
if (REPO / 'scripts/assets/download_assets.py').is_file():
    from scripts.assets.download_assets import read_manifest
    helpers.read_manifest = read_manifest
