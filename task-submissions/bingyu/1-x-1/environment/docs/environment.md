# CPU Docker Environment

This image provides a Conda-managed Python 3.12 environment with CPU-only PyTorch and the common search, embedding, indexing, document-processing, media, HTTP, and service packages used by the tasks. Installed Python packages include `torch`, `torchvision`, `torchcodec`, `numpy`, `transformers`, `sentence-transformers`, `FlagEmbedding`, `deepspeed`, `faiss-cpu`, `bm25s`, `rank-bm25`, `pyserini`, `hnswlib`, `qdrant-client`, `docling`, `marker-pdf`, `pdf2image`, `pypdfium2`, `CairoSVG`, `av`, `imageio`, `imageio-ffmpeg`, `tiktoken`, `fastapi`, `uvicorn`, `python-multipart`, `requests`, `aiohttp`, `openai`, and `pydantic-settings`.

The task Python interpreter and its installed packages are available at `/opt/conda/bin/python`. Use `/opt/conda/bin/python` and `/opt/conda/bin/pip` when invoking Python or installing packages.

The image also includes JDK 21, FFmpeg, Poppler utilities, Cairo, Git, curl, `jq`, `build-essential`, `ca-certificates`, `libffi`, `libgomp`, `netbase`, `netcat`, `procps`, `tzdata`, `unzip`, and the related system runtime libraries.

## Dataset file formats

The full corpus is under `/task/data/corpus/`. The small public example under
`/task/data/example/` uses the same binary formats. All multibyte fields are
**little-endian**, and fields and arrays are stored consecutively with no padding.
Read dimensions from the file headers so the same reader works on both corpora.

### `vectors.u8bin`

| Byte offset | Type and count | Meaning |
| --- | --- | --- |
| 0 | `uint32`, 1 value | Number of document vectors, `N` |
| 4 | `uint32`, 1 value | Vector dimension, `d` |
| 8 | `uint8`, `N * d` values | Vectors in row-major order, shape `(N, d)` |

Document ID `i` is the zero-based row `i`. The file size is `8 + N * d` bytes.
The full corpus has `N = 10000000`, `d = 192`, and a file size of
`1920000008` bytes. Cast vector values to `float32` or `float64` before
subtraction and squaring to avoid uint8 overflow when computing squared L2 distances.

### `metadata.spmat`

This file stores a document-by-tag matrix in compressed sparse row (CSR) format.
`N` is the number of documents, `T` the number of possible tags, and `nnz` the
number of stored entries.

| Byte offset | Type and count | Meaning |
| --- | --- | --- |
| 0 | `int64`, 1 value | Number of document rows, `N` |
| 8 | `int64`, 1 value | Number of tag columns, `T` |
| 16 | `int64`, 1 value | Number of stored entries, `nnz` |
| 24 | `int64`, `N + 1` values | CSR row pointers, `indptr` |
| `24 + 8 * (N + 1)` | `int32`, `nnz` values | Zero-based tag IDs, `indices` |
| `24 + 8 * (N + 1) + 4 * nnz` | `float32`, `nnz` values | Entry values, `data` |

For document `i`, its entries occupy the half-open interval
`[indptr[i], indptr[i + 1])`. A tag in `indices` belongs to that document only
when the corresponding value in `data` is nonzero. Missing or zero-valued entries
mean the tag is absent. `indptr[0] = 0` and `indptr[N] = nnz`; document IDs match
the vector rows above.

The file size is `24 + 8 * (N + 1) + 8 * nnz` bytes. The full corpus has
`N = 10000000`, `T = 200386`, `nnz = 108210476`, and a file size of
`945683840` bytes.

### Minimal read-only loading example

This example maps the arrays without loading the entire corpus into RAM.
In the submitted build entry point, use the paths supplied through `--vectors`
and `--metadata` instead of assuming fixed paths.

```python
from pathlib import Path
import numpy as np

root = Path("/task/data/corpus")  # Use /task/data/example for the small corpus.
vector_path = root / "vectors.u8bin"
metadata_path = root / "metadata.spmat"

n, d = map(int, np.fromfile(vector_path, dtype="<u4", count=2))
vectors = np.memmap(vector_path, mode="r", dtype="u1", offset=8, shape=(n, d))

rows, n_tags, nnz = map(int, np.fromfile(metadata_path, dtype="<i8", count=3))
assert rows == n
indptr = np.memmap(metadata_path, mode="r", dtype="<i8", offset=24, shape=(n + 1,))
indices_offset = 24 + 8 * (n + 1)
indices = np.memmap(metadata_path, mode="r", dtype="<i4",
                    offset=indices_offset, shape=(nnz,))
values = np.memmap(metadata_path, mode="r", dtype="<f4",
                   offset=indices_offset + 4 * nnz, shape=(nnz,))

doc_id = 0
start, end = map(int, indptr[doc_id:doc_id + 2])
document_tags = indices[start:end][values[start:end] != 0]
document_vector = vectors[doc_id]
```
