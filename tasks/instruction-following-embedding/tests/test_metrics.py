"""Tests of ranking direction, denominators, relevance gates and numerical validity."""
import copy
import math
from pathlib import Path
import sys
import unittest

import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'environment/runtime'))
from metrics import pmrr,ndcg,average_precision,evaluate_pairs,rank_vectors,reward,harmonic_pmrr,SCORING_METRIC

class MetricsTests(unittest.TestCase):
    def groups(self):
        candidates=[str(i) for i in range(1000)]
        return [{'key':s,'subset':s,'candidates':candidates,'qrels_og':{'0':1,'1':1},'qrels_changed':{'1':1},'changed_ids':['0']} for s in ['robust04','core17','news21']]
    def test_official_rank_ratio(self):
        self.assertEqual(pmrr(['a','b'],['b','a'],['a'],2),.5)
        self.assertEqual(pmrr(['b','a'],['a','b'],['a'],2),-.5)
        self.assertEqual(pmrr(['a','b'],['a','b'],['a'],2),0)
        # MTEB missing changed documents have rank len(run)+1.
        self.assertEqual(pmrr(['a','b'],['a','b'],['x'],2),0)
    def test_equal_subset_weight_and_failure_denominator(self):
        gs=self.groups();gs.append(copy.deepcopy(gs[0]));gs[-1]['key']='robust04-extra'
        rs={g['key']:[g['candidates'],list(reversed(g['candidates']))] for g in gs}
        full=evaluate_pairs(gs,rs);rs.pop('robust04-extra')
        report=evaluate_pairs(gs,rs)
        self.assertAlmostEqual(report['subsets']['robust04']['pmrr'],full['subsets']['robust04']['pmrr']/2)
        self.assertAlmostEqual(report['P'],sum(s['pmrr'] for s in report['subsets'].values())/3)
        self.assertEqual(report['subsets']['robust04']['valid'],1)
        self.assertEqual(report['subsets']['robust04']['ndcg10_og'],.5)
    def test_idcg_uses_all_qrels(self):
        self.assertLess(ndcg(['a'],{'a':1,'not-in-candidates':3}),1/3)
        self.assertEqual(average_precision(['a'],{'a':1,'missing':1}),.5)
        self.assertEqual(ndcg([],{'a':1}),0)
    def test_relevance_gate_and_normalized_score(self):
        anchors={'metric':SCORING_METRIC,'B':0,'U':.1,'rho':.8,'R0':{s:{'og':1,'changed':1} for s in ['robust04','core17','news21']}}
        report={'P':.05,'subsets':{s:{'pmrr':.05,'ndcg10_og':1,'ndcg10_changed':1} for s in anchors['R0']}}
        self.assertAlmostEqual(reward(report,anchors)[0],.5)
        report['subsets']['core17']['ndcg10_changed']=.79
        self.assertEqual(reward(report,anchors)[0],0)
        report['subsets']['core17']['ndcg10_changed']=1
        for subset in report['subsets'].values():subset['pmrr']=1
        self.assertEqual(reward(report,anchors)[0],1)
        anchors['U']=0
        with self.assertRaises(ValueError):reward(report,anchors)
    def test_harmonic_mean_penalizes_imbalance(self):
        self.assertAlmostEqual(harmonic_pmrr([.1,.2,.4]),3/(10+5+2.5))
        self.assertLess(harmonic_pmrr([.1,.2,.4]),sum([.1,.2,.4])/3)
        self.assertAlmostEqual(harmonic_pmrr([.2,.2,.2]),.2)
        self.assertGreater(harmonic_pmrr([.11,.2,.4]),harmonic_pmrr([.1,.2,.4]))
    def test_nonpositive_subset_or_malformed_metric(self):
        for values in [[0,.2,.4],[-.1,.2,.4],[0,0,0]]:
            self.assertEqual(harmonic_pmrr(values),0)
        for values in [[.1,.2],[.1,.2,float('nan')],[.1,.2,float('inf')],[.1,.2,1.1]]:
            with self.assertRaises(ValueError):harmonic_pmrr(values)
        self.assertGreater(harmonic_pmrr([1e-310,.2,.4]),0)
    def test_reward_uses_subset_harmonic_not_diagnostic_macro(self):
        anchors={'metric':SCORING_METRIC,'B':0,'U':.2,'rho':.9,'R0':{s:{'og':1,'changed':1} for s in ['robust04','core17','news21']}}
        report={'P':1,'H':1,'subsets':{s:{'pmrr':p,'ndcg10_og':1,'ndcg10_changed':1} for s,p in zip(anchors['R0'],[.1,.2,.4])}}
        self.assertAlmostEqual(reward(report,anchors)[0],harmonic_pmrr([.1,.2,.4])/.2)
        report['subsets']['news21']['pmrr']=0
        self.assertEqual(reward(report,anchors)[0],0)
        anchors.pop('metric')
        with self.assertRaises(ValueError):reward(report,anchors)
    def test_normalization_stable_ties_and_bad_vectors(self):
        q=np.ones(1024);docs=np.stack([q,2*q]);ids=['first','second']
        self.assertEqual(rank_vectors(q,docs,ids),ids)
        for invalid in [np.zeros(1024),np.ones(1023),np.full(1024,np.nan),np.full(1024,np.inf)]:
            with self.assertRaises(ValueError):rank_vectors(invalid,docs,ids)
    def test_top10_and_duplicate_results_do_not_pass(self):
        gs=self.groups();rs={g['key']:[g['candidates'][:10],g['candidates']] for g in gs}
        self.assertEqual(evaluate_pairs(gs,rs)['P'],0)
        self.assertTrue(all(s['valid']==0 for s in evaluate_pairs(gs,rs)['subsets'].values()))

if __name__=='__main__':unittest.main()
