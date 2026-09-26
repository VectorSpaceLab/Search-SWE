"""Collect linked dependency notices and runtime package metadata for image builds."""

import hashlib
import json
from pathlib import Path
import re


LEGAL = re.compile(r"^(licen[cs]e|copying|notice|patents|copyright|authors)([._-].*)?$", re.I)


def json_stream(text):
    decoder = json.JSONDecoder()
    position = 0
    while position < len(text):
        if text[position].isspace():
            position += 1
            continue
        value, position = decoder.raw_decode(text, position)
        yield value


def collect_notices(build_info, modules, goroot, output):
    """Preserve notices for every module actually linked into the Go binary."""
    output.mkdir(parents=True, exist_ok=False)
    available = {entry["Path"]: entry for entry in modules}
    rows = []
    linked = [build_info["Main"], *build_info.get("Deps", [])]
    linked.append({"Path": "go-standard-library", "Version": build_info["GoVersion"]})
    for index, dependency in enumerate(sorted(linked, key=lambda value: value["Path"])):
        path = dependency["Path"]
        if path == "go-standard-library":
            root = Path(goroot)
        else:
            entry = available[path]
            root = Path(entry.get("Replace", entry)["Dir"])
        if not root.is_dir():
            raise ValueError("Missing linked-module source directory")
        row = {"module": path, "version": dependency.get("Version"), "sum": dependency.get("Sum"),
               "replacement": dependency.get("Replace"), "notices": []}
        licensed = False
        for source in sorted(root.rglob("*")):
            if not LEGAL.fullmatch(source.name) or source.is_dir():
                continue
            if source.is_symlink() or not source.is_file() or source.stat().st_size > 2_000_000:
                raise ValueError("Unexpected module notice file")
            relative = source.relative_to(root)
            target = output / str(index) / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            data = source.read_bytes()
            target.write_bytes(data)
            row["notices"].append({"source": relative.as_posix(), "file": target.relative_to(output).as_posix(),
                                    "sha256": hashlib.sha256(data).hexdigest()})
            licensed |= source.name.lower().startswith(("license", "licence", "copying"))
        if not licensed:
            raise ValueError("Linked module has no collected license: " + path)
        rows.append(row)
    document = {"version": 1, "scope": "linked Go module and standard-library notice inventory; not legal clearance",
                "modules": rows}
    (output / "index.json").write_text(json.dumps(document, indent=2) + "\n")
    return document


def runtime_inventory(installed):
    rows = []
    for record in installed.split("\n\n"):
        fields = dict(line.split(":", 1) for line in record.splitlines() if ":" in line)
        if "P" not in fields:
            continue
        rows.append({"name": fields["P"], "version": fields["V"], "license_declared": fields.get("L"),
                     "origin": fields.get("o"), "aports_commit": fields.get("c"), "upstream_url": fields.get("U")})
    if not rows or any(not row["license_declared"] or not row["origin"] or not row["aports_commit"] for row in rows):
        raise ValueError("Incomplete runtime package license/source metadata")
    return {"version": 1, "scope": "APK-declared metadata; does not supply corresponding source or legal clearance",
            "packages": sorted(rows, key=lambda row: row["name"])}
