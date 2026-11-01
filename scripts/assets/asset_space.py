"""Read-only, size-based storage estimates for manifest-owned task inputs."""

from pathlib import Path
import shutil


def filesystem(path):
    parent = Path(path).expanduser().resolve()
    while not parent.exists():
        parent = parent.parent
    return parent.stat().st_dev, shutil.disk_usage(parent).free


def require_free(path, size):
    _, free = filesystem(path)
    if size > free:
        raise ValueError(f"Insufficient asset storage at {path}: need {size / 2**30:.2f} GiB free, "
                         f"available {free / 2**30:.2f} GiB")


def plan(records, *, cache_dir=None, local_data_dir=None):
    from huggingface_hub import constants, try_to_load_from_cache
    cache = Path(cache_dir or constants.HF_HUB_CACHE).expanduser().resolve()
    if cache.exists() and not cache.is_dir():
        raise ValueError(f"Hugging Face cache must be a directory: {cache}")
    volumes, locations, sources = {}, {}, set()
    cache_exists = cache.is_dir()
    total = target_growth = cache_growth = 0

    def reserve(path, growth, staging=0):
        if path not in locations:
            device, free = filesystem(path)
            locations[path] = device
            volume = volumes.setdefault(device, {"paths": [], "additional_bytes": 0,
                                                 "staging_bytes": 0, "free_bytes": free})
            volume["paths"].append(str(path))
        volume = volumes[locations[path]]
        volume["additional_bytes"] += growth
        volume["staging_bytes"] = max(volume["staging_bytes"], staging)

    for target, entry in records:
        target = Path(target).absolute()
        size = entry["size_bytes"]
        total += size
        # Stat only: checksum verification belongs to restoration. Same-size
        # corruption can require repair; per-file free-space checks cover it.
        present = target.is_file()
        existing = target.stat().st_size if present else 0
        if present and existing == size:
            reserve(target.parent, 0)
            continue
        growth = max(0, size - existing)
        target_growth += growth
        reserve(target.parent, growth, min(size, existing))
        source = entry.get("source", {})
        if "repo_id" not in source or (local_data_dir is not None and
                source.get("repo_id") == "search-swe/Search-SWE" and source.get("repo_type") == "dataset"):
            continue
        identity = tuple(source.get(key) for key in ("repo_id", "repo_type", "revision", "filename"))
        if identity in sources:
            continue
        sources.add(identity)
        cached = try_to_load_from_cache(repo_id=source["repo_id"], repo_type=source["repo_type"],
                                        revision=source["revision"], filename=source["filename"], cache_dir=cache) if cache_exists else None
        if isinstance(cached, str) and Path(cached).is_file() and Path(cached).stat().st_size == size:
            continue
        cache_growth += size
        reserve(cache, size)
    # Also show the cache's free space when every source is already cached.
    reserve(cache, 0)
    for volume in volumes.values():
        volume["additional_bytes"] += volume.pop("staging_bytes")
    return {"task_bytes": total, "task_additional_bytes": target_growth,
            "cache_path": str(cache), "cache_additional_bytes": cache_growth,
            "filesystems": list(volumes.values())}


def describe(plan, target):
    print(f"Task inputs: {plan['task_bytes'] / 2**30:.2f} GiB total under {target}; "
          f"about {plan['task_additional_bytes'] / 2**30:.2f} GiB additional.")
    print(f"HF cache: {plan['cache_path']}; about {plan['cache_additional_bytes'] / 2**30:.2f} GiB additional "
          "(shared sources reused). Set HF_HUB_CACHE to choose another cache disk.")
    for volume in plan["filesystems"]:
        print(f"Filesystem at {volume['paths'][0]}: about {volume['additional_bytes'] / 2**30:.2f} GiB needed, "
              f"{volume['free_bytes'] / 2**30:.2f} GiB available.")
    print("Size-based estimate; checksum repairs may need extra space. "
          "Allow additional space for Docker images/builds, task scratch files and results.")


def validate(plan):
    for volume in plan["filesystems"]:
        if volume["additional_bytes"] > volume["free_bytes"]:
            raise ValueError(f"Insufficient asset storage at {volume['paths'][0]}: "
                             f"need about {volume['additional_bytes'] / 2**30:.2f} GiB, "
                             f"available {volume['free_bytes'] / 2**30:.2f} GiB. "
                             "Choose a checkout/cache on a larger disk or free space before retrying.")
