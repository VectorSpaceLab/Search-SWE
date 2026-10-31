"""Discover a checkout and read task metadata without executing task code."""

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import tomllib


VARIABLE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::[-?][^}]*)?\}")
REPOSITORY_URL = "https://github.com/VectorSpaceLab/Search-SWE.git"


def is_repo(root):
    return (root / "tasks").is_dir() and (root / "scripts/run_task.py").is_file()


def preference_path():
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "search-swe/repository.json"


def saved_repo():
    try:
        value = json.loads(preference_path().read_text()).get("repo")
        if isinstance(value, str) and Path(value).is_absolute():
            root = Path(value).resolve()
            if is_repo(root):
                return root
    except (OSError, ValueError, AttributeError):
        pass
    return None


def remember_repo(root):
    path = preference_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            json.dump({"repo": str(root.resolve())}, stream)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def clone_repo(destination):
    destination = Path(destination).expanduser().resolve()
    if destination.exists() and (not destination.is_dir() or any(destination.iterdir())):
        raise ValueError(f"Choose a new or empty directory; {destination} already contains files")
    if not shutil.which("git"):
        raise ValueError("Install Git to clone Search-SWE, or select an existing checkout")
    destination.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "clone", "--depth", "1", "--branch", "main", "--single-branch", "--",
                    REPOSITORY_URL, str(destination)],
                   env={**os.environ, "GIT_TERMINAL_PROMPT": "0"}, check=True)
    if not is_repo(destination):
        raise ValueError(f"The cloned repository at {destination} is missing Search-SWE task files")
    return destination


def find_repo(explicit=None):
    selected = explicit or os.environ.get("SEARCH_SWE_REPO")
    if selected:
        candidates = [Path(selected).expanduser().resolve()]
    else:
        here = Path.cwd().resolve()
        candidates = [here, *here.parents, Path(__file__).resolve().parents[2]]
    for root in candidates:
        if is_repo(root):
            return root
    if not selected and (saved := saved_repo()) is not None:
        return saved
    raise ValueError("Select a Search-SWE checkout with --repo PATH or SEARCH_SWE_REPO, "
                     "or run search-swe configure in a terminal to choose or clone one. "
                     f"Clone manually: git clone {REPOSITORY_URL}")


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
