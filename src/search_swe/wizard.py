"""Interactive choices are collected before configuration is written or work starts."""

import questionary

from .configuration import EFFORTS, PI_KEYS, Setting
from .model_catalog import MODEL_ID, ModelCompleter, eligible, load_models


def ask(question):
    value = question.ask()
    if value is None:
        raise KeyboardInterrupt
    return value


def select_setting(current, args):
    harnesses = ["codex", "claude-code", "pi"]
    agent = args.agent or ask(questionary.select("Harness", choices=harnesses,
                            default=current.agent if current.agent in harnesses else "codex"))
    providers = ["direct"] if agent == "pi" else ["openrouter", "direct"]
    provider = args.provider or (providers[0] if len(providers) == 1 else
        ask(questionary.select("Provider", choices=providers,
                               default=current.provider if current.provider in providers else providers[0])))
    if provider not in providers:
        raise ValueError("Pi uses the supported direct-provider adapters")
    same_route = (agent, provider) == (current.agent, current.provider)
    model, metadata = args.model, None
    if model is None and provider == "openrouter":
        default = current.model if same_route else ("anthropic/claude-opus-5.5" if agent == "claude-code" else Setting().model)
        model, metadata = openrouter_model(agent, default, args)
    elif model is None and agent == "pi":
        model = ask(questionary.select("Model", choices=list(PI_KEYS),
                    default=current.model if current.model in PI_KEYS else next(iter(PI_KEYS))))
    elif model is None:
        model = ask(questionary.text("Model ID for the direct endpoint",
                    default=current.model if same_route else "", validate=lambda value: bool(value.strip()))).strip()
    levels = ["default", "off", "minimal", *EFFORTS] if agent == "pi" else ["default", *EFFORTS]
    effort = args.reasoning_effort
    if effort is None:
        parameters = metadata.get("supported_parameters") if metadata else None
        if parameters is not None and not {"reasoning", "reasoning_effort"}.intersection(parameters):
            print("This model lists no reasoning parameter; using its default configuration.")
            effort = "default"
        else:
            default = current.effort if same_route and model == current.model and not args.model else "default"
            choices = [questionary.Choice("Model/config default (omit effort override)", value="default"),
                       *levels[1:]]
            effort = ask(questionary.select("Reasoning / thinking level", choices=choices,
                         default=default if default in levels else "default"))
    return Setting(agent, provider, model, effort).validate()


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
    if agent == "claude-code" and not default.startswith("anthropic/"):
        default = ""
    def validate(value):
        value = value.strip() or default
        if not MODEL_ID.fullmatch(value):
            return "Select a model or enter its complete provider/model ID"
        if agent == "claude-code" and not value.startswith("anthropic/"):
            return "Claude Code on OpenRouter uses an anthropic/ model"
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


def credential(name, env, updates, *, optional=False):
    if env.get(name):
        action = ask(questionary.select(f"{name}: configured", choices=["Keep existing", "Replace"]))
        if action == "Keep existing":
            return
    if name == "VERIFIER_OPENAI_API_KEY" and env.get("AGENT_OPENROUTER_API_KEY"):
        reuse = ask(questionary.select("Trajectory judge key", choices=["Enter a separate key", "Reuse my OpenRouter agent key"]))
        if reuse.startswith("Reuse"):
            updates[name] = env[name] = env["AGENT_OPENROUTER_API_KEY"]
            return
    prompt = name + (" (optional; Enter to skip)" if optional else " (required)")
    if name.endswith("API_KEY"):
        value = ask(questionary.password(prompt, validate=lambda v: True if optional or v.strip() else "A key is required"))
    else:
        defaults = {"AGENT_OPENAI_BASE_URL": "https://api.openai.com/v1",
                    "ANSWER_JUDGE_BASE_URL": "https://openrouter.ai/api/v1"}
        value = ask(questionary.text(prompt, default=env.get(name) or defaults.get(name, ""),
                    validate=lambda v: True if optional or v.strip() else "A value is required"))
    if value:
        updates[name] = env[name] = value


def configure_agent(setting, env, updates):
    for name in sorted(setting.required()):
        credential(name, env, updates)


def select_tasks(catalog):
    query = ask(questionary.text("Filter tasks by name (Enter for all)"))
    candidates = [task for task in catalog.values() if query.lower() in task.name.lower()]
    if not candidates:
        raise ValueError("No tasks match the filter")
    choices = [questionary.Choice(
        f"{task.name} · {task.cpus} CPU / {task.memory_mb / 1024:g} GiB / {task.gpus} GPU · assets {task.asset_bytes / 2**30:.2f} GiB",
        value=task.name) for task in candidates]
    names = ask(questionary.checkbox("Tasks (Space to select; Enter to confirm)", choices=choices,
                validate=lambda values: True if values else "Select at least one task"))
    return [catalog[name] for name in names]


def configure_task_services(tasks, env, updates):
    required = set().union(*(task.required_variables() for task in tasks))
    optional = set().union(*(task.optional_keys() for task in tasks)) - required
    print("Configure evaluation services required by the selected tasks.")
    for name in sorted(required):
        credential(name, env, updates)
    if optional and ask(questionary.confirm("Configure optional APIs available to submitted programs?", default=False, auto_enter=False)):
        for name in sorted(optional):
            credential(name, env, updates, optional=True)


def concurrency(value):
    if value is not None:
        return value
    mode = ask(questionary.select("Execution", choices=["Sequential", "Parallel"]))
    if mode == "Sequential":
        return 1
    return int(ask(questionary.text("Maximum simultaneous tasks (CPU/RAM/GPU also limit admission)", default="2",
               validate=lambda v: True if v.isdigit() and int(v) > 0 else "Enter a positive integer")))


def gpu_pool():
    from .resources import gpu_inventory
    idle = [gpu for gpu in gpu_inventory() if gpu["idle"]]
    if not idle:
        raise ValueError("No idle GPU available for the selected tasks")
    choices = [questionary.Choice(f"GPU {gpu['index']} · {gpu['uuid']}", value=gpu["uuid"], checked=True) for gpu in idle]
    return ",".join(ask(questionary.checkbox("GPU pool for this batch", choices=choices,
                       validate=lambda values: True if values else "Select at least one GPU")))
