import sys
import unittest
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'environment/runtime'))
from gold import feasible, top_ids

class GoldTests(unittest.TestCase):
    def test_boundary_ties_use_ids_and_nonfinite_scores_never_enter(self):
        scores=np.array([3.,1.,1.,float('nan'),0.,1.])
        np.testing.assert_array_equal(top_ids(scores,np.ones(6,dtype=bool),3),[4,1,2])
    def test_only_requested_properties_require_finite_values_and_bounds_include_edges(self):
        properties=np.array([[1.,np.nan,0,0,0,0],[2.,3.,0,0,0,0],[np.nan,0,0,0,0,0]])
        np.testing.assert_array_equal(feasible(properties,{}),[True,True,True])
        np.testing.assert_array_equal(feasible(properties,{'mol_wt':[1.,2.]}),[True,True,False])
        np.testing.assert_array_equal(feasible(properties,{'logp':[None,3.]}),[False,True,True])
    def test_small_and_empty_references(self):
        scores=np.array([1.,0.])
        np.testing.assert_array_equal(top_ids(scores,np.array([True,True])),[1,0])
        self.assertEqual(len(top_ids(scores,np.array([False,False]))),0)

if __name__=='__main__': unittest.main()
