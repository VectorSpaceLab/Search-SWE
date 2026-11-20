"""Harbor interfaces shared by the CLI and checkout launchers."""

from importlib.metadata import version

from packaging.version import Version

HARBOR_VERSION = Version(version("harbor"))

if HARBOR_VERSION >= Version("0.25"):
    from harbor.agents.agent_auth_resolution import (
        PROVIDERS, ModelConnectionSpec, ResolvedModelConnection, resolve_model_connection,
    )
else:
    from harbor.agents.model_connection import (
        PROVIDERS, ModelConnectionSpec, ResolvedModelConnection, resolve_model_connection,
    )


def provider_variables(access):
    if hasattr(access, "api_key_candidate_names"):
        return access.api_key_candidate_names, access.base_url_candidate_names, access.extra_env_names
    return access.api_key_envs, access.base_url_envs, access.extra_envs


def legacy_gpu_override():
    # Native Docker device reservations were introduced in Harbor 0.24.
    return HARBOR_VERSION < Version("0.24")


def resolve_trial_network_plan(task, agent, environment, step, **kwargs):
    from harbor.trial.network_policy import resolve_trial_network_plan as resolve
    from harbor.models.trial.config import VerifierConfig

    if HARBOR_VERSION.release[:2] >= (0, 25):
        kwargs["trial_verifier_cfg"] = VerifierConfig()
    return resolve(task, agent, environment, step_cfg=step, **kwargs)
