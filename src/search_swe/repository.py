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

from . import __version__


VARIABLE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::[-?][^}]*)?\}")
REPOSITORY_URL = "https://github.com/VectorSpaceLab/Search-SWE.git"


def is_repo(root):
    if not (root / "tasks").is_dir():
        return False
    if (root / "scripts/evaluation/run_task.py").is_file():
        return True
    # Recognize existing checkouts before enforcing the CLI/backend version contract.
    try:
        project = tomllib.loads((root / "pyproject.toml").read_text()).get("project", {})
        return project.get("name") == "search-swe"
    except (OSError, ValueError, AttributeError):
        return False


def checkout_version(root):
    try:
        project = tomllib.loads((root / "pyproject.toml").read_text())["project"]
        value = project["version"] if project.get("name") == "search-swe" else "unknown"
        return value if isinstance(value, str) else "unknown"
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return "unknown"


def compatible_version(version):
    series = ".".join(__version__.split(".")[:2])
    return isinstance(version, str) and re.fullmatch(re.escape(series) + r"\.\d+", version) is not None


def check_compatibility(root):
    """Patch releases share a CLI/checkout contract within their release series."""
    version = checkout_version(root)
    series = ".".join(__version__.split(".")[:2])
    if not compatible_version(version):
        raise ValueError(f"Search-SWE CLI {__version__} needs a {series}.x checkout; "
                         f"{root} declares {version}. Update this checkout to the {series}.x release series "
                         "(preserve local changes), or use --repo to select a compatible checkout. "
                         "Updating the Python package alone does not update task/backend files.")
    if not (root / "scripts/evaluation/run_task.py").is_file():
        raise ValueError(f"Search-SWE checkout at {root} is missing its evaluation launcher. "
                         "Restore or update the checkout, or select a complete checkout with --repo.")


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
        result.update(name for name, options in self.configuration().items() if options.get("required"))
        return result

    def variables(self):
        result = set()
        for phase in ("environment", "agent", "verifier"):
            for value in self.config.get(phase, {}).get("env", {}).values():
                result.update(VARIABLE.findall(str(value)))
        return result

    def configuration(self):
        settings = self.config.get("metadata", {}).get("configuration", {})
        if not isinstance(settings, dict):
            raise ValueError(f"{self.name}: metadata.configuration must be a table")
        for name, options in settings.items():
            if (name not in self.variables() or not isinstance(options, dict)
                    or set(options) - {"required", "description", "guidance"}
                    or type(options.get("required", False)) is not bool
                    or any(not isinstance(options.get(key, ""), str) for key in ("description", "guidance"))):
                raise ValueError(f"{self.name}: invalid configuration guidance for {name}; use a referenced host variable and required/description/guidance fields")
        return settings

    def optional_variables(self):
        result = self.variables()
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
