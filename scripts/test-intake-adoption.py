import json
import pathlib
import sqlite3
import tempfile
import unittest
from contextlib import closing
from unittest.mock import patch
from chat_identity import approved_intake, resolve
from adopt_intake_identity import adopt
import signal_queue as q

class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=pathlib.Path(self.tmp.name)
        self.review=self.path/'review.sqlite3';self.db=q.connect(':memory:')
        self.binding={'channel':'whatsapp','identity':'123@lid','person_id':'P1','active':True,
                      'verification':{'source':'crm_review_approval','request_id':'R1'}}
        self.msg={'logical_id':'m1','revision':'r1','channel':'whatsapp','account':'owner','direction':'inbound',
                  'external_identity':'123@lid','occurred_at':None,'text':'price for 2 units','metadata':{},'completeness':'text_only','system':False}
        self.eid=q.put_evidence(self.db,self.msg,{'status':'unverified','person_id':None})
        self.db.execute("INSERT INTO analysis_tasks(id,state,attempts) VALUES('T1','succeeded_local_validation',3)")
        self.db.execute("INSERT INTO task_evidence VALUES('T1',?)",(self.eid,));self.db.commit()
        self.plan={'task_id':'T1','operations':[{'collection':'people','id':'P1','body':{'id':'P1','craWhatsappIdentity':'123@lid'}}]}
        with closing(sqlite3.connect(self.review)) as db, db:
            db.executescript('CREATE TABLE requests(id,status,decision,payload);CREATE TABLE crm_intake_outbox(request_id,state,plan);CREATE TABLE crm_intake_readback(request_id,record_id,payload);')
            db.execute('INSERT INTO requests VALUES(?,?,?,?)',('R1','approved',json.dumps({'selectedChoiceId':'create_intake'}),json.dumps({'executionPlan':self.plan})))
            db.execute('INSERT INTO crm_intake_outbox VALUES(?,?,?)',('R1','succeeded',json.dumps(self.plan)))
            db.execute('INSERT INTO crm_intake_readback VALUES(?,?,?)',('R1','P1',json.dumps(self.plan['operations'][0]['body'])))
    def tearDown(self):self.db.close();self.tmp.cleanup()
    def test_exact_proof_and_rejection(self):
        self.assertIsNotNone(approved_intake(self.binding,self.review))
        self.assertIsNone(approved_intake(dict(self.binding,person_id='P2'),self.review))
        path=self.path/'bindings.json';path.write_text(json.dumps({'bindings':[self.binding]}))
        self.assertEqual(resolve('whatsapp','123@lid',path,self.review)['person_id'],'P1')
        with closing(sqlite3.connect(self.review)) as db, db:db.execute("UPDATE crm_intake_outbox SET state='pending'")
        self.assertEqual(resolve('whatsapp','123@lid',path,self.review)['status'],'unverified')
    def test_preserve_history_and_queue_only_new_message(self):
        with self.db:self.assertEqual(adopt(self.db,self.binding,self.review),1)
        resolved={'status':'verified','person_id':'P1','verification':self.binding['verification']}
        with self.db:
            q.put_evidence(self.db,self.msg,resolved)
            self.assertEqual(q.create_tasks(self.db,'rules','model'),0)
            self.assertEqual(adopt(self.db,self.binding,self.review),0)
            q.put_evidence(self.db,dict(self.msg,logical_id='m2'),resolved)
            self.assertEqual(q.create_tasks(self.db,'rules','model'),1)
        self.assertEqual(tuple(self.db.execute("SELECT state,attempts FROM analysis_tasks WHERE id='T1'").fetchone()),('succeeded_local_validation',3))
    def test_revised_source_blocks_adoption(self):
        with self.db:q.put_evidence(self.db,dict(self.msg,revision='r2'),{'status':'unverified','person_id':None})
        with self.assertRaises(ValueError):adopt(self.db,self.binding,self.review)
    def test_no_diana_context_leak(self):
        (self.path/'crm-contexts.json').write_text(json.dumps({'customers':[{'person_id':'P1','purchase_contexts':[{'opportunity_id':'O1'},{'opportunity_id':'O2'}]}]}))
        with patch.object(q,'DATA',self.path):context=q.customer_context('P1')
        self.assertEqual(context['known_order_numbers'],[])
        self.assertNotIn('Diana',json.dumps(context))
        self.assertEqual(len(context['verified_crm_snapshot']['purchase_contexts']),2)

if __name__=='__main__':unittest.main()
