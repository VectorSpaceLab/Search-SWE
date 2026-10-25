# Search-SWE Task Authoring Contract

Read this reference before creating or changing a task package. Paths in code
blocks and backticks are relative to the target Search-SWE repository root,
unless they begin with `/` (container paths). The skill may be installed
elsewhere. Use the target checkout's validators and the published image tags
documented in `docker/README.md`.

## Use reviewed tasks as bounded precedents

Before scaffolding, inspect one or two closest reviewed packages already merged
into the base branch under `tasks/`. Record that base revision alongside the
selected paths. Prefer similarity in this order when it affects the design:

1. engineering objective and the evaluation/baseline shape;
2. deterministic verifier versus model judge, plus artifact-transfer interface;
3. external retrieval/LLM resources and network/credential boundaries;
4. CPU/GPU execution and input/asset layout.

Use repository search to shortlist candidates rather than reading every task:

```bash
rg -n 'objective|gpus|environment_mode' tasks -g task.toml
```

For selected candidates, inspect `task.toml`, `raw-instruction.md` (if present),
`instruction.md`, `assets.json`,
both Docker/Compose definitions, environment/resource docs, and the verifier
entrypoint relevant to the comparison. This discovery is source inspection,
not permission to execute an existing task, download its assets, or use its
APIs. Record the exact task paths, why they match, which structural patterns are
being reused, and intentional differences. If no close analogue exists, record
that and follow the current scaffold and contracts directly.

Use the current skill, repository validators, Harbor schema, `docker/README.md`,
and documented task contract to resolve conflicts with reference packages.
Reuse structure and reviewed implementation patterns. Independently establish
the new task's name/authors, datasets and HF paths, hashes/pins, thresholds/baselines, provider/model allowlists, resource
budgets, licenses/provenance, instructions, and hidden evaluation design. Do not
copy a value merely to make the new package resemble its precedent.

## Define the task before packaging it

A task must describe one independently buildable, repeatable, and objectively
scorable agent job. Before editing files, settle the points that affect its
design:

- descriptive task name, engineering objective and starting system or inputs;
- exact submission interface and artifact paths;
- primary metric, pass gates, baseline (when applicable), and timeout behavior;
- public inputs versus verifier-only inputs, including provenance and license;
- CPU or GPU execution, memory/storage needs, network access, and permitted APIs;
- the required trajectory integrity audit and whether answer quality additionally
  needs a subjective judge.

Ask the maintainer when any of these are ambiguous. Do not invent a data source,
license, expected metric, hidden split, paid service, or GPU requirement.

Public validation and hidden evaluation inputs should be disjoint enough to
measure generalization while exercising the same documented interface. A task
must not reward hard-coded answers, test modification, verifier manipulation,
or access to a reference solution.

## Required package contract

Create each new package at `tasks/<task-name>/` in the contribution branch, with
`task.name = "search-swe/<task-name>"` and actual `task.toml` authors. Choose a
concise descriptive name of at most five lowercase hyphen-separated words,
starting with a letter and otherwise using letters/digits. The `task-` prefix
and `all` are reserved. Check uniqueness against the current base and active PRs.
A PR may contain multiple tasks. Review each package and verify its pinned
upstream or official assets; publish official inputs only when needed. Complete
validation, then merge with a merge commit to preserve authors.
Revise existing tasks in place. `scripts/check_tasks.py` reuses
`scripts/check_release.py`, which requires these non-empty files:

```text
tasks/<task-name>/
├── instruction.md
├── task.toml
├── assets.json
├── environment/
│   ├── Dockerfile
│   └── docker-compose.yaml
└── tests/
    ├── Dockerfile
    ├── docker-compose.yaml
    └── test.sh
```

Also provide the repository conventions that apply to the task:

```text
├── raw-instruction.md            # Structured source for the natural-language request
├── VALIDATION.md                 # Design, checks, trials, feedback, final revision
├── .gitignore                    # Ignore /data/, /models/, jobs, credentials, caches
├── README.md                     # Author-facing overview and provenance
├── environment/
│   ├── .dockerignore              # Exclude secrets/caches from the build context
│   ├── docs/environment.md       # Exact tools/runtime visible to the agent
│   ├── docs/available_resources.md  # Only resources actually injected
│   └── starter/                  # Optional starter implementation
├── model-metadata/               # Small, bundled model metadata when needed
└── tests/
    ├── .dockerignore
    ├── grader.py                 # Task metric and confined submission execution
    ├── finalize_reward.py        # Metric + required audit; separate health state
    ├── rewardkit_deepseek.py     # Current pinned trajectory backend
    ├── jailbreak_judge/codex.toml # Task-specific integrity rubric
    ├── data/                     # Small verifier-only queries/labels, when needed
    └── test_*.py                 # Actual grader and failure-case regressions
```

Use `schema_version = "1.4"`. Set `task.name` to
`search-swe/<task-name>`, give the task a version, and keep the objective,
keywords, metadata, artifact paths, timeouts, network modes, and resource
budgets mutually consistent. Follow the closest existing task for fields that
are not explained by Harbor's schema, subject to the bounded-precedent rules
above; do not copy its task-specific values.
When measuring improvement against a supplied starting system/model, document
that baseline and the comparison criterion.

Use the task title as the README's level-one heading, followed by these
level-two headings in order: `Task Metadata`, `Change Log`,
`Difficulty Explanation`, `Verification Explanation`, and `References`.
Metadata covers identity, authors, inputs, metric and resource budgets.
Explain engineering difficulty with any measured evidence, and document scoring,
limits, setup and validation under verification; use level-three headings as needed.
List the papers, datasets or methods actually referenced by the task, or `None`.
New tasks start at `1.0.0` with a dated `Added initial task` changelog entry.
Keep the README and `task.version` aligned as the task evolves; retain original
versions and fingerprints in historical validation reports. New packages keep
design, grader checks, configured-model feedback and final-revision evidence in
`VALIDATION.md`. Link externally stored evidence without copying secrets or
author-only solutions into the package; preserve existing tasks' historical
report names when revising them.

Search-SWE release packages use a separate verifier:

```toml
[verifier]
environment_mode = "separate"
```

Declare every agent artifact that the separate verifier or result collector
needs. Include `/logs/agent/trajectory.json` for the required trajectory audit in
every new task. Do not assume that a separate verifier can see undeclared
agent state or reconnect to the agent container's services.

## Default CPU and GPU images

The repository supplies two shared base images. They already contain the common
Search-SWE runtime; task Dockerfiles should add only task-specific files and
pinned dependencies.

| Hardware | First line of both Dockerfiles | `task.toml` |
| --- | --- | --- |
| CPU (default) | `FROM docker.io/hanhainebula/search-swe-base:cpu-py3.12-1.0.0` | `gpus = 0` |
| NVIDIA GPU | `FROM docker.io/hanhainebula/search-swe-base:gpu-cu13.0-py3.12-1.0.0` | `gpus = 1` |

Apply the selected image to **both** `environment/Dockerfile` and
`tests/Dockerfile`. A task is CPU by default. Select the GPU image only when the
agent or verifier actually executes GPU work; merely handling model files does
not make a task a GPU task.

For a GPU task, both Compose overlays must request one NVIDIA device:

```yaml
services:
  main:
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
```

CPU Compose files must not contain an NVIDIA reservation. Keep the image,
`gpus` value, and both Compose files aligned. If a task cannot use the matching
shared image, stop and ask the maintainer before introducing a third base image.
Treat `docker/README.md` as the source of truth if published versions change.

For a local GPU trial, use the shared launcher's optional
`--gpu-device <host-index-or-UUID>`. It carries one resolved UUID into both
phases using per-run Compose copies. Keep the package's default `count: 1`
requests and document any task-specific GPU capacity requirement in its README.
Install the target checkout's pinned coding-agent CLIs in the agent Dockerfile;
the current versions are defined in `scripts/harness_versions.py`.

Choose resources from the task workload. Keep CPU/RAM values in TOML, both
Compose overlays and resource docs consistent, including explicit swap limits
and any cgroup/RSS guards. Validate actual enforcement where the metric depends
on it. Derive each supervisor window from all nested stages, repeats and
cleanup rather than copying another task's timeout.

Pin task-specific package and system dependencies. Do not use `latest`, clone a
moving branch during a build, copy a host virtual environment, or depend on a
developer's local image/cache. The Docker build context is its containing
directory, so `COPY` sources must stay under `environment/` or `tests/`.
Never copy verifier data, tests, credentials, or a reference solution into the
agent image.

## Data, models, and Compose mounts

Large fixed inputs belong under task-root `data/` or `models/`, not in Git and
not inside a Docker build context. Record every such file in `assets.json`:

- `schema_version` is `1`;
- `path` is below `data/` or `models/`;
- `size_bytes` and the lowercase SHA-256 describe the exact file;
- Hugging Face sources include `repo_id`, `repo_type`, a 40-hex immutable
  commit in `revision`, and a safe repository-relative `filename`;
- bundled small metadata may use `local_path` and must match the same size/hash;
- file `mode` is `"0644"` by default or `"0600"` for private inputs;
  `directory_modes` maps private subdirectories below `models/` to `"0700"`.
  Prepare host permissions before mounting read-only, using a download owner
  distinct from submission UID 10001. Private inputs must also be omitted from
  the agent's mounts; permissions alone do not hide them from its root user.

For manifest, mount, and credential examples when adding fixed inputs or APIs,
read [assets-and-resources.md](assets-and-resources.md). No downloaded inputs
means `{"schema_version": 1, "files": []}`; an empty manifest must not disguise
missing inputs required by the instruction.

Do not commit restored runtime assets. The task-level `.gitignore` should at
least contain `/data/` and `/models/`. Publishing files or changing the external
Hugging Face dataset is a separate mutation and requires explicit maintainer
authorization; creating a task package does not grant it.

Mount only the inputs each phase needs, read-only, with paths relative to the
Compose file. For host bind mounts, use `bind.create_host_path: false` so a
missing asset fails rather than becoming an empty directory. The agent may
receive public corpus/training/validation inputs and `environment/docs/`; the
verifier receives the minimum fixed assets needed for grading. Verifier-only
queries, labels, and grading code belong in `tests/` and are copied by
`tests/Dockerfile`, never mounted into the agent environment.

`tests/data/` is hidden from the running agent, not secret from people who can
read this public repository. Do not put credentials, private licensed data, or
other secrets there.

## Instructions and visible resources

`raw-instruction.md` is the structured authoring source; `instruction.md` is
the complete agent-facing contract rewritten as a realistic request. Follow
[instruction-rewrite.md](instruction-rewrite.md) and preserve these facts in
both versions:

- the goal and current starter state;
- absolute input/output paths and file formats;
- required command, function, service, or artifact interfaces;
- ordering, precision, concurrency, performance, and resource constraints that
  affect correctness;
- what may and may not be changed;
- available public validation data and a practical self-check;
- high-level verification behavior without exposing hidden answers or private
  scoring internals. Public correctness/performance gates belong in the
  instruction; do not hide a required threshold merely because it is tested.

Do not hide a correctness requirement only in the grader. Conversely, do not
mention `solution/`, reveal hidden cases/labels, or tell the agent how reward is
implemented. Keep the structured source outside agent mounts and Docker COPY
paths; never point the rewritten instruction to it as an easier alternate task.

Keep `environment/docs/environment.md` synchronized with the actual base image,
task additions, paths, CPU/GPU capability, and available commands. An
`available_resources.md` must list only APIs/models/endpoints actually injected
for that task, including restrictions and environment-variable names but never
credential values. Keep agent credentials separate from verifier/judge
credentials in `task.toml`.

Choose the narrowest applicable resource profile: no external resource,
retrieval/embedding/reranking only, generative LLM only, or both retrieval and
generation. When adapting an existing resource document, preserve its exact
provider/model allowlists, endpoint restrictions, credential-handling rules,
and full-score jailbreak penalty. Do not broaden access simply because another
task uses a less restricted profile.

## Verifier and reward design

Prefer deterministic programmatic checks for task metrics that code can measure.
Every new task also includes a verifier-side trajectory integrity audit; use an
additional answer-quality judge only where that dimension is subjective. Pin
tooling and configuration, adapt the audit rubric to the actual task, and
verify its healthy acceptance/rejection and failure behavior. Follow
[verifier-contract.md](verifier-contract.md) for the generated reports, stage
budgets and separation of candidate violations from invalid measurements.

The separate verifier must be self-contained. Its Dockerfile copies `tests/`
to `/tests` and installs pinned verifier-only dependencies. Protect hidden data,
grader code, logs, and reward files from the submitted program. When running
untrusted submission commands, use an unprivileged user and explicit timeouts
where practical.

`tests/test.sh` must fail closed:

- initialize `/logs/verifier/reward.txt` (and any reward JSON) to zero before
  evaluation;
- write numeric, finite rewards in `[0, 1]` on every success/failure path;
- use absolute paths and propagate meaningful nonzero exit statuses;
- bound evaluation, service startup, and judge calls with timeouts;
- clean up submission-owned background processes;
- retain useful diagnostics under `/logs/verifier/` without leaking secrets;
- grade observable behavior, not an irrelevant implementation choice.

If multiple dimensions are emitted, keep every `reward.json` value numeric and
make its `reward` field agree with `reward.txt`. Deterministic task correctness
should not silently become positive when an integrity or required judge fails.

An author-only known-good implementation may be used to validate solvability,
but do not expose it through the environment or verifier. Do not add a public
`solution/` unless the maintainers explicitly request it.

## Task-local documentation

Keep each ordinary task contribution inside `tasks/<task-name>/`. Its README
must explain required credentials, optional submission APIs, hardware, phase
policies, input restore, and validation commands. `task.toml` is the
machine-readable source; `environment/docs` describes only submission-visible
resources. Shared docs describe the framework, not a task inventory, and shared
tests discover packages from `tasks/*/task.toml`. Do not edit shared docs/tests,
`.env.example`, or workflow lists just to register a task.

## Validation checklist

Read [validation.md](validation.md) for execution prerequisites, GPU backend
compatibility, negative cases, and interpreting repository test failures.
