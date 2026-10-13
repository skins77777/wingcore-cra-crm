import copy
import unittest
from purchase_qualification import evaluate,evaluate_all

def fact(value,scope='O1'):
    return {'value':value,'person_id':'P1','opportunity_id':scope,'support_status':'verified_semantic_support',
            'references':[{'id':'E1','revision':'r1','quote':'model A, 2 units, active'}]}

class Tests(unittest.TestCase):
    def setUp(self):
        self.e={'E1':{'active':True,'person_id':'P1','revision':'r1','text':'model A, 2 units, active'}}
        self.p={'person_id':'P1','opportunity_id':'O1','current_stage':'询盘','facts':{
            'product_model':fact('A'),'quantity':dict(fact('2'),unit='pcs',scope='this_purchase'),
            'procurement_status':fact('active')}}
        self.c={'person_id':'P1','country':'Uzbekistan','country_verification':'human_confirmation'}
    def test_all_three_and_active(self):self.assertEqual(evaluate(self.p,self.e,self.c)['proposed_stage'],'需求确认')
    def test_missing_destination_stays_inquiry(self):self.assertIsNone(evaluate(self.p,self.e,{})['proposed_stage'])
    def test_paused_does_not_advance(self):
        self.p['facts']['procurement_status']['value']='paused'
        self.assertEqual(evaluate(self.p,self.e,self.c)['outcome'],'paused_or_cancelled')
    def test_quantity_cannot_cross_purchase(self):
        self.p['facts']['quantity']['opportunity_id']='O2'
        self.assertIn('本次采购数量（多项目需对应具体项目）',evaluate(self.p,self.e,self.c)['missing_fields'])
    def test_revised_or_revoked_evidence_blocks(self):
        for field,value in [('active',False),('revision','r2'),('person_id','P2')]:
            e=copy.deepcopy(self.e);e['E1'][field]=value
            self.assertIsNone(evaluate(self.p,e,self.c)['proposed_stage'])
    def test_unreviewed_model_value_does_not_pass(self):
        self.p['facts']['quantity']['support_status']='model_output_only'
        self.assertIsNone(evaluate(self.p,self.e,self.c)['proposed_stage'])
    def test_multi_project_total_is_not_breakdown(self):
        self.p['multi_project']=True;self.p['facts']['quantity']['value']='10000'
        self.assertIsNone(evaluate(self.p,self.e,self.c)['proposed_stage'])
    def test_no_silent_zero_or_non_finite(self):
        for value in ('0','-1','NaN','Infinity'):
            self.p['facts']['quantity']['value']=value
            self.assertIsNone(evaluate(self.p,self.e,self.c)['proposed_stage'])
    def test_later_stage_is_not_regressed(self):
        self.p['current_stage']='报价';self.assertEqual(evaluate(self.p,self.e,self.c)['outcome'],'preserve_current_stage')
    def test_country_from_other_person_is_not_used(self):
        self.c['person_id']='P2';self.assertIsNone(evaluate(self.p,self.e,self.c)['proposed_stage'])
    def test_reference_quote_must_exist(self):
        self.p['facts']['quantity']['references'][0]['quote']='10000 units'
        self.assertIsNone(evaluate(self.p,self.e,self.c)['proposed_stage'])
    def test_duplicate_purchase_rejected(self):
        with self.assertRaises(ValueError):evaluate_all({'schema_version':1,'purchases':[self.p,self.p]},self.e,{'P1':self.c})

if __name__=='__main__':unittest.main()
