"""Check the compiled public baseline against independent FP64 enumeration."""
import json
import ctypes
from pathlib import Path
import sys
import tempfile
import unittest
import numpy as np


@unittest.skipUnless(Path('/task/tools/libmaxsim.so').is_file(), 'requires built CPU task image')
class ExactTests(unittest.TestCase):
    def test_variable_lengths_negative_scores_and_ties(self):
        sys.path.insert(0, '/task/tools')
        from exact_search import ExactSearch
        rng = np.random.default_rng(1729)
        lengths = np.asarray([1, 3, 16, 31, 220], dtype='i8')
        offsets = np.r_[0, lengths.cumsum()].astype('<i8')
        vectors = rng.normal(size=(offsets[-1],128)).astype('<f4')
        query = rng.normal(size=(32,128)).astype('f4')
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)
            offsets.tofile(p/'offsets.i64');vectors.tofile(p/'vectors.f32')
            (p/'ids.json').write_text(json.dumps(list(map(str,range(len(lengths))))))
            e=ExactSearch(tmp)
            ids,scores=e.search(query)
            fp64=np.asarray([(vectors[offsets[i]:offsets[i+1]].astype('f8') @ query.astype('f8').T).max(0).sum() for i in range(len(lengths))])
            expected=np.lexsort((np.arange(len(lengths)),-fp64))
            np.testing.assert_array_equal(ids,expected)
            np.testing.assert_allclose(scores,fp64[ids],rtol=2e-6,atol=1e-4)
            del e
            vectors.fill(1);vectors.tofile(p/'vectors.f32');query.fill(-1)
            e=ExactSearch(tmp);ids,scores=e.search(query)
            np.testing.assert_array_equal(ids,np.arange(len(lengths)))
            np.testing.assert_array_equal(scores,np.full(len(lengths),-4096.0))


@unittest.skipUnless(Path('/task/tools/baseline/libcandidate.so').is_file(), 'requires built CPU task image')
class CandidateTests(unittest.TestCase):
    def test_native_collection_matches_unique_and_resets_bitset(self):
        rng=np.random.default_rng(617)
        documents=rng.integers(0,131,size=4096,dtype=np.int32)
        documents[:8]=[0,63,64,127,128,130,64,0]
        seen=np.full(3, np.iinfo(np.uint64).max,dtype=np.uint64)
        output=np.empty(131,dtype=np.int32)
        library=ctypes.CDLL('/task/tools/baseline/libcandidate.so')
        library.collect_candidates.argtypes=[ctypes.c_void_p]*2+[ctypes.c_int64]*2+[ctypes.c_void_p,ctypes.c_int64,ctypes.c_void_p]
        library.collect_candidates.restype=ctypes.c_int64
        for labels in [np.r_[np.arange(8),[-1,-1,2,3]],
                       rng.integers(-1,len(documents),size=12000),
                       np.asarray([-1,-1]),np.asarray([4,4,5])]:
            labels=np.ascontiguousarray(labels,dtype=np.int64)
            count=library.collect_candidates(documents.ctypes.data,labels.ctypes.data,
                len(labels),131,seen.ctypes.data,len(seen),output.ctypes.data)
            np.testing.assert_array_equal(output[:count],np.unique(documents[labels[labels>=0]]))

    def test_candidate_kernel_against_fp64(self):
        rng=np.random.default_rng(20261020)
        offsets=np.r_[0,np.cumsum([1,3,16,31,220])].astype('<i8')
        vectors=rng.normal(size=(offsets[-1],128)).astype('<f4')
        query=rng.normal(size=(32,128)).astype('<f4')
        documents=np.asarray([4,0,2,1,3,2],dtype='<i4')
        scores=np.empty(len(documents),dtype='<f4')
        library=ctypes.CDLL('/task/tools/baseline/libcandidate.so')
        library.score_candidates.argtypes=[ctypes.c_void_p]*3+[ctypes.c_int64]+[ctypes.c_void_p]*2+[ctypes.c_int]
        def run():
            library.score_candidates(vectors.ctypes.data,offsets.ctypes.data,documents.ctypes.data,
                len(documents),query.ctypes.data,scores.ctypes.data,8)
        run()
        expected=[(vectors[offsets[i]:offsets[i+1]].astype('f8') @ query.astype('f8').T).max(0).sum() for i in documents]
        np.testing.assert_allclose(scores,expected,rtol=2e-6,atol=1e-4)
        vectors.fill(1);query.fill(-1);run()
        np.testing.assert_array_equal(scores,np.full(len(documents),-4096.0))


if __name__=='__main__': unittest.main()

