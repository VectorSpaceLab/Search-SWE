import unittest
from scoring import recall, gated_reward, normalized_query_seconds


class ScoringTests(unittest.TestCase):
    def setUp(self):
        self.rows = {str(i):i for i in range(120)}
        self.truth = list(range(100))
        self.good = {'query_id':0,'results':[{'doc_id':str(i),'score':100-i} for i in range(100)]}

    def score(self, value):
        return recall(value,self.truth,self.rows,0)

    def test_full_and_missing(self):
        self.assertEqual(self.score(self.good),1)
        self.good['results']=self.good['results'][:50]
        self.assertEqual(self.score(self.good),.5)
        self.assertEqual(self.score({'query_id':0,'results':[]}),0)

    def test_duplicate_unknown_not_extra_hits(self):
        self.assertEqual(self.score({'query_id':0,'results':[{'doc_id':'0','score':1}]*99+[{'doc_id':'unknown','score':1}]}),.01)

    def test_bad_output(self):
        for item in [None,{}, {'query_id':True,'results':[]}, {'query_id':1,'results':[]},
                     {'query_id':0,'results':self.good['results']+[self.good['results'][0]]},
                     {'query_id':0,'results':[{'doc_id':'0','score':float('nan')}]},
                     {'query_id':0,'results':self.good['results'][::-1]}]:
            with self.subTest(item=item): self.assertEqual(self.score(item),0)

    def test_ties_use_corpus_order(self):
        self.assertEqual(self.score({'query_id':0,'results':[{'doc_id':'1','score':1},{'doc_id':'0','score':1}]}),0)

    def test_gates_and_denominator(self):
        self.assertEqual(gated_reward(9900,10000,100,100,50),0)
        self.assertEqual(gated_reward(9900,10000,90,100,50),.2)
        self.assertEqual(gated_reward(10000,10000,50,100,50),1)
        self.assertEqual(gated_reward(9900,10000,25,100,50),1)
        self.assertEqual(gated_reward(9899.99,10000,25,100,50),0)
        self.assertEqual(gated_reward(9900,10000,101,100,50),0)
        self.assertEqual(gated_reward(9900,10000,90,100,50,False),0)
        for bad in [0,-1,float('nan'),float('inf')]:
            self.assertEqual(gated_reward(9900,10000,bad,100,50),0)
        for baseline,reference in [(0,1),(100,100),(100,101),(100,float('nan'))]:
            with self.assertRaises(ValueError): gated_reward(9900,10000,90,baseline,reference)

    def test_common_machine_slowdown_cancels(self):
        for multiplier in [.5,1,2,3]:
            seconds=normalized_query_seconds(90*multiplier,100,100*multiplier)
            self.assertEqual(gated_reward(9900,10000,seconds,100,50),.2)
            baseline=normalized_query_seconds(100*multiplier,100,100*multiplier)
            self.assertEqual(gated_reward(9900,10000,baseline,100,50),0)
        for bad in [0,-1,float('nan'),float('inf')]:
            with self.assertRaises(ValueError): normalized_query_seconds(90,100,bad)


if __name__=='__main__': unittest.main()
