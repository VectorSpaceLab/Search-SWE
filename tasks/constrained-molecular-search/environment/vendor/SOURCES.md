# Bundled code provenance

- `apex/`: NumerionLabs/apex, commit
  `80e544eff6bbc2b09022a4f780fc9665256a884e`, retrieved from the author's
  GitHub source archive. Original CC BY-NC 4.0 license retained in `apex/LICENSE`.
- `apex_topk/`: NumerionLabs/apex_topk, commit
  `c561eaa264d7def6172fde3fe356808d9a4a3f85`, recovered from the GitHub archive comment. MIT license retained. The only
  compatibility edit is `TORCH_CUDA_ARCH_LIST="8.0"` in setup.py to compile
  for the task's A100; the upstream list omitted sm_80. Search code is unchanged.
- `cccl-8dce9c1-headers.tar.gz`: header subset (`cub/cub`, `thrust/thrust`,
  `libcudacxx/include`, `LICENSE`) from NVIDIA/cccl commit
  `8dce9c154e4d472728f3eea78e2a082a6219ccbc`. It supplies DeviceTopK and
  execution-policy headers absent from the base CUDA toolkit. All header
  notices and upstream LICENSE remain intact. No compiled objects are bundled.

Data and model terms are separate and are documented in the task README.
