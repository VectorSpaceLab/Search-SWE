# Bundled verifier inputs

These fixed inputs are shipped with the task package. `assets.json` records their
original paths, sizes and SHA-256 hashes using `source.local_path`. Run the standard
repository asset downloader before launching the task; it restores these files
to `data/` with mode `0600`, preserving the existing verifier/trusted-service
mounts. The agent does not mount this directory.

This directory is excluded from the verifier Docker build context because the
restored inputs are already mounted read-only. The task README and source records
describe their provenance and applicable data terms.
