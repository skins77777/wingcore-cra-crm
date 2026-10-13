import json
import unittest
import pathlib
import tempfile
import sqlite3
from unittest.mock import patch
from review_backend import refresh
from review_backend import db_open,decide,list_items,Conflict,encode,digest,MEMBER,WORKSPACE

class Tests(unittest.TestCase):
    def setUp(self):
        self.db=db_open(':memory:')
        self.item={'id':'R1','workspaceId':WORKSPACE,'planDigest':'a'*64,'ruleId':'R01','ruleVersion':'v1',
                   'title':'Synthetic purchase','reason':'Unknown match','status':'pending','createdAt':'2026-10-12T00:00:00+00:00',
                   'target':{'objectLabel':'person','recordLabel':'Demo'},'changes':[],
                   'evidence':[],'choices':[{'id':'C1','label':'Keep candidate','description':'Demo'}],
                   'decision':None,'execution':{'status':'not_started','message':'Not executed'},'canDecide':True}
        with self.db:self.db.execute('INSERT INTO requests VALUES(?,?,?,?,?,?,?,?)',('R1','T1','rules','context',encode(self.item),'pending',self.item['createdAt'],None))
        self.input={'id':'R1','planDigest':'a'*64,'outcome':'approved','note':'Demo','selectedChoiceId':'C1'}
    def tearDown(self):self.db.close()
    def test_repeated_decision_once(self):
        first=decide(self.db,'R1',self.input);second=decide(self.db,'R1',self.input)
        self.assertEqual(first,second)
        self.assertEqual(self.db.execute('SELECT count(*) FROM decision_audit').fetchone()[0],1)
        self.assertEqual(first['value']['execution']['status'],'manual_required')
    def test_opposite_decision_conflicts(self):
        decide(self.db,'R1',self.input)
        with self.assertRaises(Conflict):decide(self.db,'R1',dict(self.input,outcome='rejected',selectedChoiceId=None))
    def test_stale_digest_conflicts(self):
        with self.assertRaises(Conflict):decide(self.db,'R1',dict(self.input,planDigest='b'*64))
    def test_member_denied(self):
        with self.assertRaises(PermissionError):decide(self.db,'R1',self.input,'not-authorized')
    def test_bad_choice_denied(self):
        with self.assertRaises(ValueError):decide(self.db,'R1',dict(self.input,selectedChoiceId='invented'))
    def test_rejected_not_executed(self):
        value=decide(self.db,'R1',dict(self.input,outcome='rejected',selectedChoiceId=None))['value']
        self.assertEqual(value['execution']['status'],'not_started')
        self.assertFalse(value['canDecide'])
    def test_superseded_denied(self):
        with self.db:self.db.execute("UPDATE requests SET status='superseded'")
        with self.assertRaises(Conflict):decide(self.db,'R1',self.input)
    def test_actor_cannot_be_spoofed(self):
        value=decide(self.db,'R1',dict(self.input,actorLabel='Attacker',workspaceId='wrong'))['value']
        self.assertEqual(value['decision']['actorLabel'],'Leeyu YIHE01')
        self.assertEqual(value['workspaceId'],WORKSPACE)
    def test_pagination_total(self):
        for i in range(2,6):
            with self.db:self.db.execute('INSERT INTO requests VALUES(?,?,?,?,?,?,?,?)',('R'+str(i),'T1','rules','context',encode(dict(self.item,id='R'+str(i))),'pending',self.item['createdAt'],None))
        page=list_items(self.db,limit=2)
        self.assertEqual(page['total'],5)
        self.assertEqual(len(page['values']),2)
        second=list_items(self.db,limit=2,cursor=page['nextCursor'])
        self.assertEqual(len(second['values']),2)
        self.assertFalse({v['id'] for v in page['values']}&{v['id'] for v in second['values']})
    def test_rule_change_invalidates_before_decision(self):
        with tempfile.TemporaryDirectory() as directory:
            root=pathlib.Path(directory)
            (root/'crm-foundation').mkdir()
            (root/'crm-foundation/chat-signal-rules.md').write_text('Changed business rules',encoding='utf-8')
            with sqlite3.connect(root/'signal.sqlite3') as signal:
                signal.executescript("CREATE TABLE analysis_tasks(id TEXT,state TEXT); CREATE TABLE candidates(state TEXT); CREATE TABLE evidence(id TEXT,external_identity TEXT,channel TEXT,active INTEGER); CREATE TABLE task_evidence(task_id TEXT,evidence_id TEXT); INSERT INTO analysis_tasks VALUES('T1','succeeded');")
            signal.close()
            with patch('review_backend.ROOT',root):refresh(self.db,root)
            self.assertEqual(self.db.execute("SELECT status FROM requests WHERE id='R1'").fetchone()[0],'superseded')
            with self.assertRaises(Conflict):decide(self.db,'R1',self.input)
    def test_approval_and_outbox_saved_once(self):
        item=dict(self.item,executionPlan={'plan_digest':'synthetic','operations':[]},choices=[{'id':'create_intake','label':'Create synthetic','description':'Isolated test'}])
        with self.db:self.db.execute('UPDATE requests SET payload=? WHERE id=?',(encode(item),'R1'))
        input=dict(self.input,selectedChoiceId='create_intake')
        with patch('review_backend.enabled',return_value=True):
            first=decide(self.db,'R1',input);second=decide(self.db,'R1',input)
        self.assertEqual(first,second)
        self.assertEqual(first['value']['execution']['status'],'queued')
        self.assertEqual(self.db.execute('SELECT count(*) FROM crm_intake_outbox').fetchone()[0],1)
        self.assertEqual(self.db.execute('SELECT count(*) FROM decision_audit').fetchone()[0],1)
    def test_rejection_never_queues_intake(self):
        with self.db:self.db.execute('UPDATE requests SET payload=? WHERE id=?',(encode(dict(self.item,executionPlan={'operations':[]})),'R1'))
        with patch('review_backend.enabled',return_value=True):decide(self.db,'R1',dict(self.input,outcome='rejected',selectedChoiceId=None))
        self.assertEqual(self.db.execute('SELECT count(*) FROM crm_intake_outbox').fetchone()[0],0)
    def test_summary_approval_outbox_once_and_private_plan_hidden(self):
        item=dict(self.item,contextUpdatePlan={'plan_digest':'synthetic'},choices=[{'id':'update_context','label':'Update','description':'Demo'}])
        with self.db:self.db.execute('UPDATE requests SET payload=?',(encode(item),))
        with patch('review_backend.enabled',return_value=True),patch('review_backend.update_current'):
            first=decide(self.db,'R1',dict(self.input,selectedChoiceId='update_context'))
            second=decide(self.db,'R1',dict(self.input,selectedChoiceId='update_context'))
        self.assertEqual(first,second)
        self.assertNotIn('contextUpdatePlan',first['value'])
        self.assertEqual(first['value']['execution']['status'],'queued')
        self.assertEqual(self.db.execute('SELECT count(*) FROM crm_update_outbox').fetchone()[0],1)
    def test_summary_rejection_does_not_queue(self):
        with self.db:self.db.execute('UPDATE requests SET payload=?',(encode(dict(self.item,contextUpdatePlan={'plan_digest':'synthetic'})),))
        decide(self.db,'R1',dict(self.input,outcome='rejected',selectedChoiceId=None))
        self.assertEqual(self.db.execute('SELECT count(*) FROM crm_update_outbox').fetchone()[0],0)
    def test_summary_invalid_proof_rolls_back_approval(self):
        from crm_update_executor import PlanConflict
        item=dict(self.item,contextUpdatePlan={'plan_digest':'synthetic'},choices=[{'id':'update_context','label':'Update','description':'Demo'}])
        with self.db:self.db.execute('UPDATE requests SET payload=?',(encode(item),))
        with patch('review_backend.enabled',return_value=True),patch('review_backend.update_current',side_effect=PlanConflict('source_changed')):
            with self.assertRaises(PlanConflict):decide(self.db,'R1',dict(self.input,selectedChoiceId='update_context'))
        self.assertEqual(self.db.execute('SELECT status FROM requests').fetchone()[0],'pending')
        self.assertEqual(self.db.execute('SELECT count(*) FROM crm_update_outbox').fetchone()[0],0)

if __name__=='__main__':unittest.main()
