import copy
import unittest
from r02_signal_adapter import choose,extract,verified_inputs

class Tests(unittest.TestCase):
    def setUp(self):
        self.row={'id':'E2','revision':'r1','active':True,'person_id':'P1','direction':'inbound','completeness':'text_only',
                  'occurred_at':'2026-10-12T02:00:00+00:00','text':'Please proceed with 2 pcs of MODEL A.'}
        self.p={'person_id':'P1','opportunity_id':'O1','current_stage':'询盘','facts':{'product_model':{
            'value':'MODEL A','support_status':'verified_semantic_support','references':[{'occurred_at':'2026-10-11T02:00:00+00:00'}]}}}
        self.c={'person_id':'P1','country':'Uzbekistan','country_verification':'human_confirmation'}
    def test_explicit_request_qualifies(self):self.assertEqual(extract(self.row,self.p,self.c)['qualification']['proposed_stage'],'需求确认')
    def test_chinese_explicit(self):
        self.row['text']='请继续采购 MODEL A，数量 2 件。'
        self.assertEqual(extract(self.row,self.p,self.c)['purchase']['facts']['quantity']['value'],'2')
    def test_no_partial_number(self):
        self.row['text']='Please proceed with 10,000 units of MODEL A.'
        self.assertEqual(extract(self.row,self.p,self.c)['purchase']['facts']['quantity']['value'],'10000')
        self.row['text']='Please proceed with 1000,000 units of MODEL A.';self.assertIsNone(extract(self.row,self.p,self.c))
    def test_questions_condition_negation_and_future_not_auto(self):
        for text in ['Please proceed with 2 pcs of MODEL A?','Do not proceed with 2 pcs of MODEL A.',
                     'If tests pass, please proceed with 2 pcs of MODEL A.','We may buy 2 pcs of MODEL A.',
                     'Please proceed with 2 pcs of MODEL A. But not yet.']:
            self.row['text']=text;self.assertIsNone(extract(self.row,self.p,self.c))
    def test_outbound_is_not_customer_intent(self):
        self.row['direction']='outbound';self.assertIsNone(extract(self.row,self.p,self.c))
    def test_country_conflict_not_auto(self):
        self.row['text']='Please proceed with 2 pcs of MODEL A for delivery to Canada.'
        self.assertIsNone(extract(self.row,self.p,self.c))
    def test_ambiguous_existing_purchases_not_auto(self):
        self.assertIsNone(choose(self.row,[self.p,dict(self.p,opportunity_id='O2')],self.c))
    def test_old_message_cannot_resume_latest_pause(self):
        self.p['facts']['status']={'references':[{'occurred_at':'2026-10-13T02:00:00+00:00'}]}
        self.assertIsNone(extract(self.row,self.p,self.c))
    def test_multiple_projects_not_auto(self):
        self.p['multi_project']=True;self.assertIsNone(extract(self.row,self.p,self.c))
    def test_missing_country_keeps_inquiry(self):
        self.assertIsNone(extract(self.row,self.p,{})['qualification']['proposed_stage'])
    def test_later_pause_blocks_older_clear_request(self):
        later=dict(self.row,id='E3',occurred_at='2026-10-12T03:00:00+00:00',text='Please pause for now.')
        self.assertIsNone(verified_inputs(self.row,[self.p],self.c,{'E2':self.row,'E3':later}))

if __name__=='__main__':unittest.main()
