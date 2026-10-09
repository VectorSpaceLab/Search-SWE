# Fixed inputs, mounts, and external resources

Read when adding data, models, services, or API access. Paths here are relative
to the target repository root; example names must be adapted to the actual
task. Nothing in this reference grants permission to publish or use paid APIs.

## Manifest construction

Keep downloadable fixed files outside the build contexts, under
`data/` or `models/` in the selected package (initially
`task-submissions/<first-name-slug>/<1|2>-x-<positive-ordinal>`, later `tasks/<final-id>`).
Ignore both directories in Git. Hidden
queries/labels and grading code go in `tests/`, not the public asset bundle.
For a verifier-only corpus stored in `data/verifier/`, mount only public
subdirectories into the agent; never mount all of `data/` in that case.

Each `assets.json` entry has this shape (values below are placeholders, not
valid checksums/revisions to submit):

```json
{
  "schema_version": 1,
  "files": [{
    "path": "data/corpus.jsonl",
    "size_bytes": 1234,
    "sha256": "REPLACE_WITH_COMPUTED_SHA256",
    "source": {
      "repo_id": "YOUR_ACCOUNT/search-swe-development",
      "repo_type": "dataset",
      "revision": "REPLACE_WITH_PUBLISHED_40_HEX_COMMIT",
      "filename": "development/corpus.jsonl"
    }
  }]
}
```

Compute `size_bytes` from the file size and SHA-256 from the actual bytes (for
example `sha256sum FILE`). Do not reuse another task's hash or fabricate a
published revision. A model source uses its original `repo_id`, `repo_type`
`"model"`, fixed commit and filename. A small bundled model metadata source can
instead be `{"local_path": "model-metadata/model/config.json"}`; it still
requires matching size/hash and is restored under `models/`.

Paths must be relative, unique, and contain no `..` or backslashes. Optional
file modes are `"0644"` and `"0600"`; private model directories can be declared
as `"directory_modes": {"models/private-model": "0700"}` at manifest root.
Do not attempt `chmod` on read-only mounted files during verification.

## Development and incremental publication

For pre-promotion development, use an authorized **personal public temporary HF
dataset** with manifest, provenance and license; pin its immutable 40-hex SHA in
submission `assets.json`. The downloader accepts arbitrary HF repositories:

```bash
python scripts/download_assets.py --task-path task-submissions/alice/1-x-1
python scripts/download_assets.py --task-path task-submissions/alice/1-x-1 --verify-only
```

After the maintainer assigns the final ID in the same PR, prepare new official
files at `tasks/<final-id>/...`. The target checkout's
`scripts/prepare_hf_upload.py` accepts a current official manifest snapshot,
the final task package and **only new data**. It verifies hashes, preserves old
entries, refuses collisions and stages new files plus a merged manifest offline.
Read the bundled [publication workflow](publication.md) for exact commands
and approval boundaries. Append/update
HF `SOURCES.md`, dataset card/license and LFS metadata. Never delete old assets.
Publish through a **HF community PR (`create_pr=True`)** with your personal
account, or ask a maintainer to mirror reviewed public files. Never share or
request an official token. Refresh a stale manifest snapshot before merging.

The official HF change must merge **before** pinning the resulting official SHA
in final `assets.json` and merging the GitHub task PR. Do not pin the community
PR SHA or use a mutable branch. Keep original model pins unchanged. Official
publication is separately authorized; helpers do not upload. Do not publish
permanent official paths containing temporary task IDs.

## Full dataset audit (maintainers)

For unpublished data, prepare an authorized local HF staging directory with
`README.md`, `SOURCES.md`, `.gitattributes`, `manifest.json`, and `tasks/` files.
Its manifest has `schema_version: 1` and `files` entries containing dataset-relative
`path`, `size_bytes`, and `sha256`. It must match the checkout's complete dataset
inventory, not just new files. Contributors normally use the incremental
helper above instead; it does not need all old assets. Full local checks support:

```bash
python scripts/check_release.py --hf-data /path/to/hf-data \
  --verify-data --allow-unpublished
```

Only staged `search-swe/Search-SWE` dataset sources may have null revisions in
this mode. Publication is a separate approval step; pin the resulting commit
and validate without `--allow-unpublished` before claiming remote reproducibility.

## Mount only what each phase needs

Agent overlay at `environment/docker-compose.yaml`, for a task with a shared
corpus and public validation directory:

```yaml
services:
  main:
    volumes:
      - type: bind
        source: ../data/corpus.jsonl
        target: /task/data/corpus.jsonl
        read_only: true
        bind:
          create_host_path: false
      - type: bind
        source: ../data/validation
        target: /task/data/validation
        read_only: true
        bind:
          create_host_path: false
      - type: bind
        source: ./docs
        target: /task/docs
        read_only: true
        bind:
          create_host_path: false
```

The verifier overlay at `tests/docker-compose.yaml` separately mounts the corpus
it needs; docs there use `../environment/docs`. It does not inherit agent mounts.
Hidden queries/labels are copied by `tests/Dockerfile` to `/tests/data`. Merge
these volume entries with any GPU reservations, rather than overwriting them.
Declare agent-produced artifacts at the **top level** of `task.toml`, before
`[task]`, e.g. `artifacts = ["/app/submission"]`.

Additional services are optional. If necessary, use a `main` service plus
sidecars with healthchecks and health-based dependencies, not fixed sleeps.
Reach sidecars by service name, not `localhost`. Export any state needed by a
separate verifier as declared artifacts; live service state is not transferred.

## Network and credentials

Default to no task network where feasible. For required APIs, document exact
providers, endpoints and model IDs in `environment/docs/available_resources.md`
and use hostnames, not URLs, in network allowlists. Different phases may have
different network needs, including coding-agent setup/provider connectivity;
verify the installed Harbor backend's enforcement rather than assuming a task
policy automatically configures the coding agent's transport.

Credentials are resolved at runtime, not during image builds. For example:

```toml
[environment.env]
JINA_API_KEY = "${JINA_API_KEY:-}"

[verifier.env]
OPENAI_BASE_URL = "${VERIFIER_OPENAI_BASE_URL:-}"
OPENAI_API_KEY = "${VERIFIER_OPENAI_API_KEY:-}"
```

Only add a variable if that phase needs it. Empty injected values are not proof
of a working API. The verifier must also filter the environment of submitted
commands so judge keys are not passed to untrusted code. Do not print, persist,
or expose credentials through logs, artifacts, Docker layers or CLI arguments.

Choose no API, retrieval-only, generation-only, or both based on the task's
approved resource policy. Reusing a profile does not authorize extra providers
or models. A mandatory integrity/judge failure must not silently count as a
pass. For deterministic grading, no RewardKit or model judge is required;
when using RewardKit, install a fixed compatible version in the verifier image
and verify its actual CLI/configuration before enabling live judging.
