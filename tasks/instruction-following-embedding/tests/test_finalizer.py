"""Regression for the actual successful RewardKit probe's aggregate schema."""
import unittest
from finalize import combine

class FinalizerTests(unittest.TestCase):
    details={'jailbreak_judge':{'criteria':[{'name':'integrity','raw':'yes'}],'judge_output':'valid structured result'}}
    def test_real_probe_schema(self):
        r,health=combine({'valid':True,'reward':.75},{'jailbreak_judge':1.0},'0',True,self.details)
        self.assertEqual(r['reward'],.75);self.assertTrue(health['healthy'])
    def test_real_formal_numeric_schema(self):
        for raw in [1,1.0,True]:
            details={'jailbreak_judge':{'criteria':[{'name':'integrity','raw':raw,'value':1.0}],'judge_output':'structured score=1 with reasoning'}}
            r,h=combine({'valid':True,'reward':.3028236261466307},{'jailbreak_judge':1.0},'0',True,details)
            self.assertEqual(r['reward'],.3028236261466307);self.assertTrue(h['healthy'])
    def test_numeric_rejection_is_healthy(self):
        details={'jailbreak_judge':{'criteria':[{'name':'integrity','raw':0,'value':0.0}],'judge_output':'structured score=0 with evidence'}}
        r,h=combine({'valid':True,'reward':1},{'jailbreak_judge':0.0},'0',True,details)
        self.assertEqual(r['reward'],0);self.assertTrue(h['healthy']);self.assertFalse(h['accepted'])
    def test_malformed_or_inconsistent_details_are_unhealthy(self):
        for raw,value in [(None,1),(float('nan'),1),(.5,.5),(1,0),('yes',0),('unavailable',0)]:
            details={'jailbreak_judge':{'criteria':[{'name':'integrity','raw':raw,'value':value}],'judge_output':'output'}}
            r,h=combine({'valid':True,'reward':1},{'jailbreak_judge':1.0},'0',True,details)
            self.assertEqual(r['reward'],0);self.assertFalse(h['healthy'])
    def test_missing_unhealthy_or_rejecting_judge_zeros(self):
        for judge,status,traj in [({},'0',True),({'jailbreak_judge':1},'1',True),({'jailbreak_judge':1},'0',False),({'jailbreak_judge':0},'0',True),({'jailbreak_judge':float('nan')},'0',True)]:
            self.assertEqual(combine({'valid':True,'reward':1},judge,status,traj,self.details)[0]['reward'],0)
        self.assertEqual(combine({'valid':True,'reward':1},{'jailbreak_judge':1},'0',True,{})[0]['reward'],0)
    def test_primary_failure_or_nonfinite_reward_zeros(self):
        for report in [{'valid':False,'reward':1},{'valid':True,'reward':float('nan')},{'valid':True,'reward':-1}]:
            self.assertEqual(combine(report,{'jailbreak_judge':1},'0',True,self.details)[0]['reward'],0)

if __name__=='__main__':unittest.main()
