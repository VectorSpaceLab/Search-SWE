# Binary input formats

Both corpus and example files use the layouts below. All multibyte fields are
little-endian; arrays are consecutive with no padding.

## `vectors.u8bin`

| Byte offset | Type and count | Meaning |
| --- | --- | --- |
| 0 | `uint32`, 1 | Number of vectors, `N` |
| 4 | `uint32`, 1 | Vector dimension, `d` |
| 8 | `uint8`, `N * d` | Row-major vector array of shape `(N, d)` |

Document ID `i` identifies row `i`.

## `metadata.spmat`

Document-by-tag matrix in compressed sparse row (CSR) format.

| Byte offset | Type and count | Meaning |
| --- | --- | --- |
| 0 | `int64`, 1 | Number of documents, `N` |
| 8 | `int64`, 1 | Number of tag columns, `T` |
| 16 | `int64`, 1 | Number of stored entries, `nnz` |
| 24 | `int64`, `N + 1` | Row pointers, `indptr` |
| `24 + 8 * (N + 1)` | `int32`, `nnz` | Tag IDs, `indices` |
| `24 + 8 * (N + 1) + 4 * nnz` | `float32`, `nnz` | Entry values, `data` |

Row `i` occupies entries `[indptr[i], indptr[i + 1])`. A nonzero entry means that
the document has the corresponding tag. Missing or zero-valued entries mean
absence. Document rows correspond to vector rows.
