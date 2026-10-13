import json
import pathlib
import tempfile
import unittest
import uuid
from unittest.mock import patch
from contextlib import closing
import signal_queue as q
import r02_runtime as runtime
import review_backend
import crm_update_executor as writer

class Remote:
    def __init__(self,record):self.record=dict(record);self.writes=0
    def read(self,*args):return dict(self.record)
    def conditional_update(self,plan):
        if self.record['updatedAt']!=plan['expected_updated_at']:raise writer.PlanConflict('remote_version_conflict')
        self.record.update(plan['after']);self.record['updatedAt']='2026-10-12T03:00:00.000Z';self.writes+=1

class Tests(unittest.TestCase):
    def test_new_message_to_verified_stage_write_without_model_or_duplicate(self):
        with tempfile.TemporaryDirectory() as directory:
            root=pathlib.Path(directory);person=str(uuid.uuid4());opportunity=str(uuid.uuid4())
            db=q.connect(root/'signal.sqlite3')
            def message(logical,text,time):return {'logical_id':logical,'revision':'r1','channel':'whatsapp','account':'owner','direction':'inbound','external_identity':'123@lid','occurred_at':time,'text':text,'metadata':{},'completeness':'text_available','system':False}
            old=q.put_evidence(db,message('old','MODEL A','2026-10-11T00:00:00+00:00'),{'status':'verified','person_id':person})
            db.execute("INSERT INTO analysis_tasks(id,state,result) VALUES('historical','succeeded',?)",(q.encode({'coverage':[],'facts':[],'uncertainties':[],'proposed_updates':[]}),))
            db.execute("INSERT INTO task_evidence VALUES('historical',?)",(old,))
            new=q.put_evidence(db,message('new','Please proceed with 2 pcs of MODEL A.','2026-10-12T02:00:00+00:00'),{'status':'verified','person_id':person})
            rules=q.digest((q.ROOT/'crm-foundation/chat-signal-rules.md').read_text(encoding='utf-8'))
            q.create_tasks(db,rules,'model');db.commit()
            evidence={r['id']:dict(r) for r in db.execute('SELECT * FROM evidence')};db.close()
            store={'schema_version':1,'purchases':[{'person_id':person,'opportunity_id':opportunity,'current_stage':'询盘','facts':{
                'product_model':{'value':'MODEL A','person_id':person,'opportunity_id':opportunity,'support_status':'verified_semantic_support',
                                 'references':[{'id':old,'revision':'r1','quote':'MODEL A'}]}}}]}
            (root/'purchase-facts.json').write_text(json.dumps(store),encoding='utf-8')
            cfg={'enabled':True,'person_ids':[person]};pol=root/'policy.json';pol.write_text(json.dumps(cfg))
            with closing(review_backend.db_open(root/'review.sqlite3')):pass
            remote=Remote({'id':opportunity,'pointOfContactId':person,'name':'Demo','craPurchaseStage':'询盘','updatedAt':'2026-10-12T00:00:00.000Z'})
            customer={'person_id':person,'country':'Uzbekistan','country_verification':'human_confirmation'}
            def mocked_inputs(_):return json.loads((root/'purchase-facts.json').read_text()),evidence,customer,remote
            with patch.object(q,'DATA',root),patch.object(runtime,'POLICY',pol),patch.object(runtime,'inputs',side_effect=mocked_inputs),patch.object(q,'sync',return_value={'status':'ok','new_tasks':0}),patch.object(q,'analyze',side_effect=AssertionError('no model needed')),patch.object(writer,'DATA',root),patch.object(writer,'read_config',return_value={'CRA_CRM_INTAKE_ENABLED':'true','CRA_CRM_INTAKE_API_KEY':'synthetic'}),patch.object(writer,'UpdateRemote',return_value=remote),patch.object(writer,'resolve',return_value={'person_id':person}):
                first=runtime.run();second=runtime.run()
            self.assertEqual(first['new_stage_plans'],1);self.assertEqual(second['new_stage_plans'],0)
            self.assertEqual(remote.writes,1);self.assertEqual(remote.record['craPurchaseStage'],'需求确认')
            with closing(review_backend.db_open(root/'review.sqlite3')) as review:
                self.assertEqual(review.execute('SELECT state FROM crm_update_outbox').fetchone()[0],'succeeded')
                public=review_backend.list_items(review,'approved')['values'][0]
                self.assertEqual(public['execution']['status'],'succeeded')
                self.assertIn('非人工审批',public['decision']['actorLabel'])
                self.assertEqual(review.execute('SELECT count(*) FROM decision_audit').fetchone()[0],0)
            with closing(q.connect(root/'signal.sqlite3')) as db:
                self.assertEqual(db.execute('SELECT count(*) FROM attempts').fetchone()[0],0)

if __name__=='__main__':unittest.main()
