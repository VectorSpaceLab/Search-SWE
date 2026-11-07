"""Data-only harness defaults and exact version selection."""

from pathlib import Path
import re
import tomllib

REGISTRY = Path(__file__).with_name("data") / "harnesses.toml"
EXACT_VERSION = re.compile(r"v?\d+(?:\.\d+){2,}(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?\Z")


def registry(root=None):
    path = Path(root) / "src/search_swe/data/harnesses.toml" if root is not None else REGISTRY
    if not path.is_file():
        path = REGISTRY
    data = tomllib.loads(path.read_text())
    if data.get("schema_version") != 1 or not isinstance(data.get("agents"), dict):
        raise ValueError("Invalid harness registry schema")
    return data


def version_argument(value):
    if value != "default" and (not isinstance(value, str) or not EXACT_VERSION.fullmatch(value)):
        raise ValueError("Use an exact harness version such as 1.2.3, or default for the repository default")
    return value


def default_version(agent, root=None):
    return registry(root)["agents"].get(agent, {}).get("version")


def resolve_version(agent, explicit=None, configured=None, root=None):
    selected = explicit if explicit is not None else configured
    if selected is None or selected == "default":
        selected = default_version(agent, root)
    if selected is not None:
        version_argument(selected)
        if agent in ("oracle", "nop"):
            raise ValueError(f"{agent} is a Harbor helper; its version is controlled by the Harbor dependency")
    return selected


def install_spec(agent, version=None, root=None):
    data = registry(root)["agents"].get(agent)
    if data is None:
        return None
    selected = resolve_version(agent, version, root=root).removeprefix("v")
    spec = {**data, "name": agent, "version": selected}
    if spec.get("installer") == "archive":
        release = spec.pop("releases", {}).get(selected)
        if not release:
            raise ValueError(f"Register a verified {agent} {selected} archive URL and SHA-512 in src/search_swe/data/harnesses.toml")
        spec.update(release)
    return spec
