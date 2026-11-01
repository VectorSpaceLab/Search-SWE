"""Interactive checkout setup, model configuration and evaluation choices."""

from pathlib import Path
import questionary

from .configuration import EFFORTS, Setting, default_model
from . import pi_models
from .model_catalog import MODEL_ID, ModelCompleter, eligible, load_models
from .repository import clone_repo, is_repo, preference_path, remember_repo
from .submission_models import model_ids, profile_for_key, setup_hint


def ask(question):
    value = question.ask()
    if value is None:
        raise KeyboardInterrupt
    return value


def select_repository(*, offline=False):
    default = Path.home() / "Search-SWE"
    print("Choose where to keep Search-SWE tasks, downloaded assets and evaluation results.")
    print("The CLI package stays in your Python environment. This choice is remembered for future commands.")
    while True:
        choices = []
        if is_repo(default) or not offline:
            label = "Use existing checkout at" if is_repo(default) else "Clone to"
            choices.append(questionary.Choice(f"{label} {default} (default)", value="default"))
        if not offline:
            choices.append(questionary.Choice("Clone to a custom path", value="custom"))
        choices.append(questionary.Choice("Select an existing checkout", value="existing"))
        action = ask(questionary.select("Search-SWE repository", choices=choices))
        if action == "default":
            root = default.resolve()
        else:
            root = Path(ask(questionary.path("Existing checkout path" if action == "existing" else "Clone destination",
                        default=str(default), only_directories=True,
                        validate=lambda value: bool(value.strip()))).strip()).expanduser().resolve()
        if not is_repo(root):
            if action == "existing" or offline:
                print(f"No Search-SWE checkout found at {root}. Choose the root directory of a Search-SWE repository.")
                continue
            if root.exists() and (not root.is_dir() or any(root.iterdir())):
                print(f"{root} already contains files. Choose a new or empty directory.")
                continue
            if not ask(questionary.confirm(f"Clone Search-SWE into {root}?", default=True, auto_enter=False)):
                raise KeyboardInterrupt
            root = clone_repo(root)
        try:
            remember_repo(root)
        except OSError as error:
            print(f"Could not remember this path ({error}); use --repo {root} for future commands.")
        else:
            print(f"Repository path saved to {preference_path()}")
        print(f"Using Search-SWE checkout: {root}")
        return root


def select_setting(current, args):
    harnesses = ["codex", "claude-code", "pi"]
    agent = args.agent or ask(questionary.select("Harness", choices=harnesses,
                            default=current.agent if current.agent in harnesses else "codex"))
    providers = ["openrouter", "direct"]
    default_provider = current.provider if agent == current.agent else "direct" if agent == "pi" else "openrouter"
    provider = args.provider or (providers[0] if len(providers) == 1 else
        ask(questionary.select("Provider", choices=providers,
                               default=default_provider if default_provider in providers else providers[0])))
    if provider not in providers:
        raise ValueError("Choose an OpenRouter or direct provider route")
    same_route = (agent, provider) == (current.agent, current.provider)
    model, metadata = args.model, None
    if model is None and provider == "openrouter":
        default = current.model if same_route else default_model(agent, provider)
        model, metadata = openrouter_model(agent, default, args)
    elif model is None and agent == "pi":
        model = pi_model(current.model if same_route else "deepseek/deepseek-flash")
    elif model is None:
        model = ask(questionary.text("Model ID for the direct endpoint",
                    default=current.model if same_route else "", validate=lambda value: bool(value.strip()))).strip()
    if agent == "pi" and provider == "direct":
        _, model_id, info = pi_models.selection(model)
        if not info["models"].get(model_id, {}).get("reasoning", True):
            metadata = {"supported_parameters": []}
    levels = ["default", "off", "minimal", *EFFORTS] if agent == "pi" else ["default", *EFFORTS]
    effort = args.reasoning_effort
    if effort is None:
        parameters = metadata.get("supported_parameters") if metadata else None
        if parameters is not None and not {"reasoning", "reasoning_effort"}.intersection(parameters):
            print("This model lists no reasoning parameter; using its default configuration.")
            effort = "default"
        else:
            default = current.effort if same_route and model == current.model else "default"
            choices = [questionary.Choice("Model/config default (omit effort override)", value="default"),
                       *levels[1:]]
            effort = ask(questionary.select("Reasoning / thinking level", choices=choices,
                         default=default if default in levels else "default"))
    return Setting(agent, provider, model, effort).validate()


def pi_model(default):
    providers = pi_models.catalog()["providers"]
    current = default.split("/", 1)[0]
    choices = [questionary.Choice(f"{name} · {info['name']}", value=name)
               for name, info in providers.items() if name != "openrouter"]
    provider = ask(questionary.select("Pi API provider", choices=choices,
                   default=current if current in providers and current != "openrouter" else "deepseek"))
    models = {f"{provider}/{name}": {"id": f"{provider}/{name}", **info}
              for name, info in providers[provider]["models"].items()}
    preferred = default if default in models else next(iter(models))
    print(f"Pi {pi_models.catalog()['version']}: {len(models)} models. Type a name or ID to search; Enter keeps {preferred}.")
    def validate(value):
        return True if (value.strip() or preferred) in models else "Select a model from this provider's Pi catalog"
    return ask(questionary.autocomplete("Pi model", choices=[], completer=ModelCompleter(models, preferred),
                validate=validate, complete_while_typing=True, reserve_space_for_menu=10)).strip() or preferred


def openrouter_model(agent, default, args):
    print("Loading OpenRouter model catalog...", flush=True)
    models, source = load_models(offline=args.offline, refresh=args.refresh_models)
    choices = {key: model for key, model in models.items() if eligible(model, agent)}
    if source == "unavailable":
        print("Model catalog unavailable; enter a full model ID manually.")
    else:
        print(f"OpenRouter: {len(choices)} matching models ({source}). Type a name or ID to search; use ↓/↑ and Enter to select.")
    if default in models and default not in choices:
        default = ""
    def validate(value):
        value = value.strip() or default
        if not MODEL_ID.fullmatch(value):
            return "Select a model or enter its complete provider/model ID"
        if value in models and value not in choices:
            return "Choose a text model with tools and the API required by this harness"
        return True
    hint = f"Enter keeps {default}. " if default else ""
    hint += "A complete model ID can also be entered manually."
    print(hint)
    model = ask(questionary.autocomplete("OpenRouter model", choices=[],
                completer=ModelCompleter(choices, default), validate=validate,
                complete_while_typing=True, reserve_space_for_menu=10,
                placeholder=default or "Search model name or ID")).strip() or default
    return model, models.get(model)


def credential(name, env, updates, *, optional=False, edit=False):
    if env.get(name, "").strip():
        if not edit:
            return
        choices = ["Keep existing", "Replace"] + (["Disable / clear"] if optional else [])
        action = ask(questionary.select(f"{name}: configured", choices=choices))
        if action == "Keep existing":
            return
        if action == "Disable / clear":
            updates[name] = env[name] = ""
            print(f"{name}: disabled for this selection; save to clear its value in the environment file.")
            return
    if name == "VERIFIER_OPENAI_API_KEY" and env.get("AGENT_OPENROUTER_API_KEY", "").strip():
        reuse = ask(questionary.select("Trajectory judge key", choices=["Enter a separate key", "Reuse my OpenRouter agent key"]))
        if reuse.startswith("Reuse"):
            updates[name] = env[name] = env["AGENT_OPENROUTER_API_KEY"]
            return
    prompt = name + (" (optional; Enter to skip)" if optional else " (required)")
    if name.endswith(("API_KEY", "TOKEN", "TOKEN_BEDROCK")):
        value = ask(questionary.password(prompt, validate=lambda v: True if optional or v.strip() else "A key is required"))
    else:
        defaults = {"AGENT_OPENAI_BASE_URL": "https://api.openai.com/v1",
                    "ANSWER_JUDGE_BASE_URL": "https://openrouter.ai/api/v1", "AWS_REGION": "us-east-1"}
        value = ask(questionary.text(prompt, default=env.get(name) or defaults.get(name, ""),
                    validate=lambda v: True if optional or v.strip() else "A value is required"))
    value = value.strip()
    if value:
        updates[name] = env[name] = value


def configure_agent(setting, env, updates, *, edit=False):
    print("Coding-agent credentials: existing values are reused; enter missing values below.")
    if setting.agent == "pi" and setting.provider == "direct":
        provider, _, info = pi_models.selection(setting.model)
        print(f"Pi API-key setup: {info['name']} ({provider}). Only this provider's credentials are requested.")
    for name in sorted(setting.required(env)):
        credential(name, env, updates, edit=edit)


def select_tasks(catalog, *, required=True):
    if not catalog:
        if required:
            raise ValueError("No tasks found in the selected checkout; choose a populated Search-SWE checkout with --repo")
        return []
    while True:
        query = ask(questionary.text("Filter tasks by name (Enter for all)")).strip()
        candidates = [task for task in catalog.values() if query.lower() in task.name.lower()]
        if candidates:
            break
        print("No tasks match. Try another filter.")
    choices = [questionary.Choice(
        f"{task.name} · {task.cpus} CPU / {task.memory_mb / 1024:g} GiB / {task.gpus} GPU · assets {task.asset_bytes / 2**30:.2f} GiB",
        value=task.name) for task in candidates]
    prompt = "Tasks (Space to select; Enter to confirm)" if required else "Tasks for service credentials (optional; Enter to skip)"
    names = ask(questionary.checkbox(prompt, choices=choices,
                validate=lambda values: True if values or not required else "Select at least one task"))
    return [catalog[name] for name in names]


def configure_task_services(tasks, env, updates, *, edit=False):
    required = set().union(*(task.required_variables() for task in tasks))
    optional = set().union(*(task.optional_variables() for task in tasks)) - required
    owners = {name: [task for task in tasks if name in task.variables()] for name in required | optional}
    print("Configure services for the selected tasks. Existing values are reused.")
    if optional:
        print("Enable submission APIs with the models, endpoints and permitted uses in each task's resource policy.")
    for task in tasks:
        if task.variables():
            print(f"{task.name}: setup in {task.path / 'README.md'}; submission API permissions in "
                  f"{task.path / 'environment/docs/available_resources.md'}")

    explained = set()

    def explain(name):
        if name in explained:
            return
        explained.add(name)
        role = "required" if name in required else "optional submission service"
        print(f"{name} ({role}; {', '.join(task.name for task in owners[name])})")
        if (profile := profile_for_key(name)) is not None:
            print(setup_hint(profile))
        if name == "VERIFIER_OPENAI_API_KEY":
            print("OpenRouter trajectory-judge key: allow deepseek/deepseek-v4.1-flash and any additional trusted judge models in the selected task READMEs.")
        if name == "ANSWER_JUDGE_MODEL_NAME":
            print("Choose a Chat Completions model for answer grading at the task's configured judge endpoint; this is independent of the coding-agent model.")
        for task in owners[name]:
            details = task.configuration().get(name, {})
            if details:
                print(f"{task.name}: {details.get('description', '')}")
                if details.get("guidance"):
                    print(details["guidance"].strip())

    for name in sorted(required):
        if edit or not env.get(name, "").strip() or profile_for_key(name) or any(name in task.configuration() for task in owners[name]):
            explain(name)
        credential(name, env, updates, edit=edit)
    for name in sorted(optional):
        if env.get(name, "").strip() and (profile_for_key(name) or any(name in task.configuration() for task in owners[name])):
            explain(name)
    if any(env.get(name, "").strip() for name in optional) and not edit:
        print("Saved optional APIs are enabled. To disable or replace one, use search-swe configure TASK --edit-credentials.")
    candidates = [name for name in sorted(optional) if edit or not env.get(name, "").strip()]
    if candidates:
        choices = []
        for name in candidates:
            profile = profile_for_key(name)
            policy = f"; required {len(model_ids(profile))}-model allowlist" if profile else ""
            choices.append(questionary.Choice(f"{name} ({', '.join(task.name for task in owners[name])}{policy})", value=name))
        names = ask(questionary.checkbox("Optional submission APIs to configure (Space to select; Enter to skip)", choices=choices))
        for name in names:
            explain(name)
            credential(name, env, updates, optional=True, edit=edit)


def concurrency(value, *, default=1):
    if value is not None:
        return value
    mode = ask(questionary.select("Execution", choices=["Sequential", "Parallel"],
                                 default="Parallel" if default > 1 else "Sequential"))
    if mode == "Sequential":
        return 1
    return int(ask(questionary.text("Maximum simultaneous tasks (CPU/RAM/GPU also limit admission)", default=str(max(2, default)),
               validate=lambda v: True if v.isdigit() and int(v) > 0 else "Enter a positive integer")))


def gpu_pool():
    from .resources import gpu_inventory
    idle = [gpu for gpu in gpu_inventory() if gpu["idle"]]
    if not idle:
        raise ValueError("No idle GPU available for the selected tasks")
    choices = [questionary.Choice(f"GPU {gpu['index']} · {gpu['uuid']}", value=gpu["uuid"], checked=True) for gpu in idle]
    return ",".join(ask(questionary.checkbox("GPU pool for this batch", choices=choices,
                       validate=lambda values: True if values else "Select at least one GPU")))
