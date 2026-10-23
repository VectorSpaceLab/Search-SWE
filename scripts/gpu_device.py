"""Select one host GPU and specialize a task's per-run Compose configuration."""

import copy
import re
import subprocess


GPU_UUID = re.compile(r"GPU-[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}\Z")


def validate_gpu_device(value):
    if not (re.fullmatch(r"[0-9]+", value) or GPU_UUID.fullmatch(value)):
        raise ValueError("--gpu-device must be one host GPU index or full GPU UUID")
    return value


def resolve_gpu_device(value):
    """Resolve against the local host once, before either phase is launched."""
    validate_gpu_device(value)
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=index,uuid", "--format=csv,noheader,nounits"],
            check=True, capture_output=True, text=True, timeout=15,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise ValueError("Cannot list host GPUs; check nvidia-smi and the NVIDIA driver") from error
    for line in result.stdout.splitlines():
        fields = [field.strip() for field in line.split(",")]
        if len(fields) != 2 or not GPU_UUID.fullmatch(fields[1]):
            raise ValueError("nvidia-smi returned an invalid GPU inventory")
        index, identity = fields
        if value.lower() == identity.lower() or (value.isdigit() and int(value) == int(index)):
            return identity
    raise ValueError(f"GPU {value!r} is not present on this host")


def select_compose_gpu(document, identity):
    """Replace the existing single-card request without changing task mounts."""
    if not GPU_UUID.fullmatch(identity):
        raise ValueError("GPU selection requires a resolved GPU UUID; use scripts/run_task.sh --gpu-device")
    selected = copy.deepcopy(document)
    devices = (selected.get("services", {}).get("main", {}).get("deploy", {})
               .get("resources", {}).get("reservations", {}).get("devices", []))
    if (len(devices) != 1 or devices[0].get("driver") != "nvidia"
            or "gpu" not in devices[0].get("capabilities", [])
            or devices[0].get("count") != 1 or "device_ids" in devices[0]):
        raise ValueError("Explicit GPU selection requires a task Compose request for one NVIDIA GPU (count: 1)")
    devices[0].pop("count")
    devices[0]["device_ids"] = [identity]
    return selected
