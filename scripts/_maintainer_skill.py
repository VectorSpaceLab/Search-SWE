"""Load the portable skill's single-source offline helpers for legacy CLIs."""
import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
path = REPO / ".agents/skills/maintain-searchswe-task/scripts/maintainer_helpers.py"
spec = importlib.util.spec_from_file_location("searchswe_maintainer_helpers", path)
helpers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helpers)
