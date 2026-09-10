#!/usr/bin/env python3
"""Configure the existing Codex trajectory audit from verifier-only settings."""

import argparse
import json
import os
from pathlib import Path
import shutil
from urllib.parse import urlsplit


def configure(template, output, home):
    names = ("OPENAI_BASE_URL", "OPENAI_API_KEY")
    values = {name: os.environ.get(name, "").strip() for name in names}
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise ValueError("missing trajectory judge settings: " + ", ".join(missing))
    base = values["OPENAI_BASE_URL"].rstrip("/")
    parsed = urlsplit(base)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username or parsed.password:
        raise ValueError("OPENAI_BASE_URL must be an absolute HTTP(S) URL without credentials")
    home.mkdir(parents=True, exist_ok=True)
    config = home / "config.toml"
    config.write_text(
        'model_provider = "trajectory_judge"\n\n'
        '[model_providers.trajectory_judge]\n'
        'name = "Trajectory judge"\n'
        f'base_url = {json.dumps(base)}\n'
        'wire_api = "responses"\n'
        'env_key = "OPENAI_API_KEY"\n'
        'supports_websockets = false\n', encoding="utf-8",
    )
    config.chmod(0o600)
    output.mkdir(parents=True, exist_ok=True)
    criterion = output / "jailbreak_judge"
    criterion.mkdir(exist_ok=True)
    shutil.copyfile(template, criterion / "codex.toml")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--template", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--home", type=Path, required=True)
    args = parser.parse_args()
    configure(args.template, args.output, args.home)
