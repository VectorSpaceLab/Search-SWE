"""Readers for the original Big-ANN u8bin and CSR spmat formats."""
from pathlib import Path

import numpy as np
from scipy.sparse import csr_matrix


def read_vectors(path):
    """Return a read-only (N, d) uint8 memory map, without normalization."""
    path = Path(path)
    shape = np.fromfile(path, dtype="<u4", count=2)
    if len(shape) != 2:
        raise ValueError("truncated u8bin header")
    rows, dimension = map(int, shape)
    if rows <= 0 or dimension <= 0 or path.stat().st_size != 8 + rows * dimension:
        raise ValueError("invalid u8bin shape or file size")
    return np.memmap(path, dtype=np.uint8, mode="r", offset=8,
                     shape=(rows, dimension))


def read_metadata(path):
    """Return document-by-tag CSR. A nonzero entry denotes tag membership."""
    path = Path(path)
    shape = np.fromfile(path, dtype="<i8", count=3)
    if len(shape) != 3:
        raise ValueError("truncated spmat header")
    rows, columns, nnz = map(int, shape)
    if min(rows, columns, nnz) < 0 or columns == 0:
        raise ValueError("invalid spmat shape")
    if path.stat().st_size != 24 + (rows + 1) * 8 + nnz * 8:
        raise ValueError("invalid spmat file size")
    pointer = np.memmap(path, dtype="<i8", mode="r", offset=24, shape=rows + 1)
    if pointer[0] != 0 or pointer[-1] != nnz or np.any(pointer[1:] < pointer[:-1]):
        raise ValueError("invalid CSR row pointers")
    offset = 24 + pointer.nbytes
    if nnz:
        indices = np.memmap(path, dtype="<i4", mode="r", offset=offset, shape=nnz)
        values = np.memmap(path, dtype="<f4", mode="r", offset=offset + nnz * 4,
                           shape=nnz)
        if np.min(indices) < 0 or np.max(indices) >= columns:
            raise ValueError("tag ID outside the metadata vocabulary")
    else:
        indices, values = np.empty(0, dtype=np.int32), np.empty(0, dtype=np.float32)
    return csr_matrix((values, indices, pointer), shape=(rows, columns), copy=False)


def validate_query(record, dimension):
    """Validate the public query contract; indexing/filter execution is not here."""
    if not isinstance(record.get("query_id"), str):
        raise ValueError("query_id must be a string")
    vector = np.asarray(record["vector"], dtype=np.float32)
    if vector.shape != (dimension,) or not np.all(np.isfinite(vector)):
        raise ValueError("query vector has invalid shape or non-finite values")
    predicate = record["filter"]
    if not isinstance(predicate, dict) or set(predicate) != {"all"}:
        raise ValueError('filter must have the form {"all": [tag IDs]}')
    if not isinstance(predicate["all"], list) or any(
        type(tag) is not int or tag < 0 for tag in predicate["all"]
    ):
        raise ValueError("tags must be nonnegative integers")
    k = record["k"]
    if type(k) is not int or not 0 <= k <= 100:
        raise ValueError("k must be an integer between 0 and 100")
    return vector, predicate, k
