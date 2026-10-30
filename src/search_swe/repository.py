"""Discover a checkout and read task metadata without executing task code."""

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import tomllib


VARIABLE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::[-?][^}]*)?\}")


def find_repo(explicit=None):
    selected = explicit or os.environ.get("SEARCH_SWE_REPO")
    if selected:
        candidates = [Path(selected).expanduser().resolve()]
    else:
        here = Path.cwd().resolve()
        candidates = [here, *here.parents, Path(__file__).resolve().parents[2]]
    for root in candidates:
        if (root / "tasks").is_dir() and (root / "scripts/run_task.py").is_file():
            return root
    raise ValueError("Select a Search-SWE checkout with --repo PATH or SEARCH_SWE_REPO, "
                     "or run from the cloned repository. Clone: git clone https://github.com/VectorSpaceLab/Search-SWE.git")


@dataclass(frozen=True)
class Task:
    name: str
    path: Path
    title: str
    cpus: int
    memory_mb: int
    gpus: int
    storage_mb: int
    asset_bytes: int
    config: dict

    @property
    def bounded(self):
        return (self.path / "tools/prepare_storage.py").is_file()

    @property
    def cpu_variable(self):
        source = (self.path / "environment/docker-compose.yaml").read_text()
        match = re.search(r"\$\{([A-Z][A-Z0-9_]*_CPUSET)(?=[:}])", source)
        return match[1] if match else None

    def required_variables(self):
        result = set()
        for key, value in self.config.get("verifier", {}).get("env", {}).items():
            if key in ("OPENAI_API_KEY", "OPENAI_BASE_URL") or key.startswith("ANSWER_JUDGE_"):
                result.update(VARIABLE.findall(str(value)))
        return result

    def optional_keys(self):
        result = set()
        for phase in ("environment", "agent", "verifier"):
            for value in self.config.get(phase, {}).get("env", {}).values():
                result.update(name for name in VARIABLE.findall(str(value)) if name.endswith("API_KEY"))
        return result - self.required_variables()


def discover(root):
    tasks = {}
    for config_path in sorted((root / "tasks").glob("*/task.toml")):
        path = config_path.parent
        config = tomllib.loads(config_path.read_text())
        resources = config["environment"]
        manifest = json.loads((path / "assets.json").read_text())
        tasks[path.name] = Task(
            path.name, path, config.get("task", {}).get("title", path.name),
            int(resources["cpus"]), int(resources["memory_mb"]), int(resources.get("gpus", 0)),
            int(resources.get("storage_mb", 0)), sum(entry["size_bytes"] for entry in manifest["files"]), config)
    return tasks


def select_tasks(catalog, names):
    names = list(dict.fromkeys(names))
    unknown = set(names) - set(catalog)
    if unknown:
        raise ValueError("Unknown task(s): " + ", ".join(sorted(unknown)) + "; use search-swe list")
    return [catalog[name] for name in names]
