"""Persistent mature public retriever service."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import baseline
if len(sys.argv) > 1 and sys.argv[1] == "serve":
    import efficient_source
    from lexical_source import MatureSource

    efficient_source.EfficientSource = MatureSource
baseline.__file__ = str(Path(__file__).resolve())
baseline.main()
