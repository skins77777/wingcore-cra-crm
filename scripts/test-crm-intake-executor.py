import copy
import unittest
from crm_intake_executor import apply_operations,validate_plan,PlanConflict
from review_plans import intake_plan
from signal_queue import digest

class RemoteFake:
    def __init__(self):self.records={};self.created=[];self.timeout_after_commit=False;self.fail_at=None
    def read(self,collection,identifier):return self.records.get(identifier)
    def create(self,collection,body):
        if self.fail_at==len(self.created):raise OSError('synthetic failure')
        self.created.append(body['id']);self.records[body['id']]=copy.deepcopy(body)
        if self.timeout_after_commit:raise TimeoutError('synthetic timeout')

class Tests(unittest.TestCase):
    def setUp(self):self.plan=intake_plan();self.remote=RemoteFake();self.checked=[]
    def execute(self):apply_operations(self.plan,self.remote,lambda identifier,record:self.checked.append(identifier))
    def resign(self):self.plan['plan_digest']=digest({k:v for k,v in self.plan.items() if k!='plan_digest'})
    def test_readback_three_records(self):
        self.execute();self.assertEqual(len(self.checked),3);self.assertEqual(len(self.remote.created),3)
    def test_repeat_does_not_create_again(self):
        self.execute();self.execute();self.assertEqual(len(self.remote.created),3)
    def test_timeout_after_commit_recovers(self):
        self.remote.timeout_after_commit=True;self.execute();self.assertEqual(len(self.remote.created),3)
    def test_human_change_never_overwritten(self):
        self.execute();self.remote.records[self.plan['operations'][0]['id']]['craCountry']='Changed manually'
        with self.assertRaises(PlanConflict):self.execute()
        self.assertEqual(self.remote.records[self.plan['operations'][0]['id']]['craCountry'],'Changed manually')
    def test_partial_completion_resume(self):
        self.remote.fail_at=1
        with self.assertRaises(OSError):self.execute()
        self.remote.fail_at=None;self.execute();self.assertEqual(len(self.remote.created),3)
    def test_no_order_endpoint(self):
        self.plan['operations'][1]['collection']='dingDans';self.resign()
        with self.assertRaises(PlanConflict):validate_plan(self.plan)
    def test_no_payment_amount_field(self):
        self.plan['operations'][1]['body']['amount']={'amountMicros':1890000000,'currencyCode':'USD'};self.resign()
        with self.assertRaises(PlanConflict):validate_plan(self.plan)
    def test_unapproved_changed_plan_digest(self):
        self.plan['operations'][1]['body']['name']='Changed'
        with self.assertRaises(PlanConflict):validate_plan(self.plan)
    def test_no_automatic_won(self):
        self.plan['operations'][1]['body']['stage']='CUSTOMER';self.resign()
        with self.assertRaises(PlanConflict):validate_plan(self.plan)
    def test_changed_context_stops_remaining_creates(self):
        def guard():
            if self.remote.created:raise PlanConflict('source_changed')
        with self.assertRaises(PlanConflict):apply_operations(self.plan,self.remote,lambda *args:None,guard)
        self.assertEqual(len(self.remote.created),1)
if __name__=='__main__':unittest.main()
