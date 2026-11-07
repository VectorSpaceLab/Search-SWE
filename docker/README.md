# Search-SWE base images

This directory contains the reproducible build contexts for the shared
Search-SWE CPU and GPU base images. The published images and their tags are
available in the [Docker Hub repository](https://hub.docker.com/r/hanhainebula/search-swe-base).

| Build context | Published tag | Use case |
| --- | --- | --- |
| [`cpu/`](cpu/) | `hanhainebula/search-swe-base:cpu-py3.12-1.0.0` | CPU tasks |
| [`gpu/`](gpu/) | `hanhainebula/search-swe-base:gpu-cu13.0-py3.12-1.0.0` | GPU tasks on an NVIDIA-capable host |

Each context contains its `Dockerfile`, pinned `requirements.txt`, and an
`environment.md` package/runtime summary. Both images target `linux/amd64`.

Task Dockerfiles add task dependencies to these bases. The shared launcher
installs the selected coding harness during setup using the central registry,
verifies its version and caches it per task image. See
[harness versions](../docs/evaluation/agents.md#harness-versions-and-installation).
Verifier images retain their independent judge dependencies.

Build from the repository root:

```bash
docker build --platform linux/amd64 \
  -t search-swe-base:cpu-py3.12-1.0.0 \
  docker/cpu

docker build --platform linux/amd64 \
  -t search-swe-base:gpu-cu13.0-py3.12-1.0.0 \
  docker/gpu
```

The GPU image includes CUDA 13.0 userspace. Running its GPU checks requires a
compatible NVIDIA driver and NVIDIA Container Toolkit on the host.
