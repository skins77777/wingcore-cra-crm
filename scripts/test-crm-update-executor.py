import copy
import unittest
import uuid
from crm_update_executor import execute,validate,PlanConflict
from signal_queue import WORKSPACE,digest

def plan():
    person=str(uuid.uuid4())
    value={'workspace_id':WORKSPACE,'collection':'people','record_id':person,'person_id':person,
           'expected_updated_at':'2026-10-12T00:00:00.000Z','before':{'craChatSummary':'old'},
           'after':{'craChatSummary':'new'},'task_id':'T1','evidence_ids':['E1']}
    value['plan_digest']=digest(value);return value

class Remote:
    def __init__(self,p):self.record={'id':p['record_id'],'updatedAt':p['expected_updated_at'],**p['before']};self.writes=0;self.race=False;self.timeout=False
    def read(self,*args):return copy.deepcopy(self.record)
    def conditional_update(self,p):
        if self.race:self.record['updatedAt']='newer';self.record['craChatSummary']='human'
        if self.record['updatedAt']!=p['expected_updated_at']:raise PlanConflict('remote_version_conflict')
        self.writes+=1;self.record.update(p['after']);self.record['updatedAt']='later'
        if self.timeout:raise TimeoutError()

class Tests(unittest.TestCase):
    def setUp(self):self.plan=plan();self.remote=Remote(self.plan)
    def test_update_and_readback(self):
        self.assertEqual(execute(self.plan,self.remote,lambda:None)['action'],'updated');self.assertEqual(self.remote.writes,1)
    def test_repeated_execution_no_second_write(self):
        execute(self.plan,self.remote,lambda:None)
        self.assertEqual(execute(self.plan,self.remote,lambda:None)['action'],'already_satisfied');self.assertEqual(self.remote.writes,1)
    def test_manual_change_before_read_blocks(self):
        self.remote.record['updatedAt']='newer'
        with self.assertRaises(PlanConflict):execute(self.plan,self.remote,lambda:None)
        self.assertEqual(self.remote.writes,0)
    def test_race_between_read_and_write_blocks(self):
        self.remote.race=True
        with self.assertRaises(PlanConflict):execute(self.plan,self.remote,lambda:None)
        self.assertEqual(self.remote.record['craChatSummary'],'human');self.assertEqual(self.remote.writes,0)
    def test_timeout_after_committed_update_recovers(self):
        self.remote.timeout=True
        self.assertEqual(execute(self.plan,self.remote,lambda:None)['action'],'recovered_readback')
    def test_forbidden_order_or_stage_field(self):
        for changes in ({'stage':'CUSTOMER'},{'amount':100},{'pointOfContactId':'other'}):
            p=dict(self.plan,after=changes,before={k:None for k in changes});p['plan_digest']=digest({k:v for k,v in p.items() if k!='plan_digest'})
            with self.assertRaises(PlanConflict):validate(p)
    def test_source_guard_stops_write(self):
        def fail():raise PlanConflict('source_changed')
        with self.assertRaises(PlanConflict):execute(self.plan,self.remote,fail)
        self.assertEqual(self.remote.writes,0)
    def test_plan_body_change_rejected(self):
        p=copy.deepcopy(self.plan);p['after']['craChatSummary']='tampered'
        with self.assertRaises(PlanConflict):execute(p,self.remote,lambda:None)

if __name__=='__main__':unittest.main()
