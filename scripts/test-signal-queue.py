import json
import pathlib
import tempfile
import unittest
import signal_queue as q

def item(revision='r1'):
    return {'logical_id':'demo','revision':revision,'channel':'email','account':'owner@example.com',
            'direction':'outbound','external_identity':'buyer@example.com','occurred_at':None,
            'text':'2 units','metadata':{},'completeness':'text_only','system':False}

VERIFIED={'status':'verified','person_id':'P1'}

class Tests(unittest.TestCase):
    def setUp(self): self.db=q.connect(':memory:')
    def tearDown(self): self.db.close()
    def seed(self):
        with self.db:
            eid=q.put_evidence(self.db,item(),VERIFIED)
            q.create_tasks(self.db,'rules','model')
        return eid,self.db.execute('SELECT id FROM analysis_tasks').fetchone()[0]
    def test_three_attempts_survive_reopen(self):
        with tempfile.TemporaryDirectory() as folder:
            path=pathlib.Path(folder)/'queue.db'
            db=q.connect(path)
            with db:
                q.put_evidence(db,item(),VERIFIED);q.create_tasks(db,'rules','model')
            task=db.execute('SELECT id FROM analysis_tasks').fetchone()[0]
            for number in (1,2,3):
                self.assertEqual(q.claim(db,task),number)
                q.finish(db,task,number,error='timeout',retryable=True)
                db.close();db=q.connect(path)
            self.assertIsNone(q.claim(db,task))
            self.assertEqual(db.execute('SELECT count(*) FROM attempts').fetchone()[0],3)
            db.close()
    def test_no_duplicate_task(self):
        self.seed()
        with self.db:
            q.put_evidence(self.db,item(),VERIFIED)
            self.assertEqual(q.create_tasks(self.db,'rules','model'),0)
    def test_revision_invalidates(self):
        eid,tid=self.seed()
        with self.db:q.put_evidence(self.db,item('r2'),VERIFIED)
        self.assertEqual(self.db.execute('SELECT state FROM analysis_tasks WHERE id=?',(tid,)).fetchone()[0],'invalidated')
        self.assertEqual(self.db.execute('SELECT active FROM evidence WHERE id=?',(eid,)).fetchone()[0],0)
    def test_identity_change_invalidates(self):
        eid,tid=self.seed()
        with self.db:q.put_evidence(self.db,item(),{'status':'verified','person_id':'P2'})
        self.assertEqual(self.db.execute('SELECT state FROM analysis_tasks WHERE id=?',(tid,)).fetchone()[0],'invalidated')
    def test_multiple_recipients_not_merged(self):
        self.assertIsNone(q.mail_identity('outbound',{'To':'a@example.com,b@example.com'}))
    def test_unknown_identity_never_queues(self):
        with self.db:
            q.put_evidence(self.db,item(),{'status':'unverified','person_id':None})
            self.assertEqual(q.create_tasks(self.db,'rules','model'),0)
    def test_decode_error_email_never_queues(self):
        for index,(completeness, text) in enumerate([('text_decode_error','corrupt synthetic text'),
                                                     ('text_only','corrupt synthetic \ufffd text')]):
            value=item(f'decode-{index}');value.update(logical_id=f'decode-test-{index}',direction='inbound',completeness=completeness,text=text)
            with self.subTest(completeness=completeness):
                with self.db:
                    q.put_evidence(self.db,value,VERIFIED)
                    self.assertEqual(q.create_tasks(self.db,'rules','model'),0)
                row=self.db.execute('SELECT eligibility FROM evidence WHERE logical_id=? AND active=1',(value['logical_id'],)).fetchone()
                self.assertEqual(row['eligibility'],'incomplete_text')
    def test_new_decode_error_invalidates_existing_pending_task(self):
        value=item();value.update(logical_id='decode-transition',direction='inbound',text='Synthetic text')
        with self.db:
            q.put_evidence(self.db,value,VERIFIED)
            q.create_tasks(self.db,'rules','model')
        task_id=self.db.execute('SELECT id FROM analysis_tasks').fetchone()[0]
        value.update(completeness='text_decode_error')
        with self.db:q.put_evidence(self.db,value,VERIFIED)
        task=self.db.execute('SELECT state,error_code FROM analysis_tasks WHERE id=?',(task_id,)).fetchone()
        self.assertEqual((task['state'],task['error_code']),('invalidated','evidence_no_longer_eligible'))
        self.assertIsNone(q.claim(self.db,task_id))
    def test_unknown_date_stays_unknown(self):
        eid,_=self.seed()
        self.assertIsNone(self.db.execute('SELECT occurred_at FROM evidence WHERE id=?',(eid,)).fetchone()[0])
    def test_wrong_coverage_rejected(self):
        output={'coverage':[],'facts':[],'uncertainties':[],'proposed_updates':[]}
        with self.assertRaises(ValueError):q.validate_output(output,{'E1'})
    def test_forged_reference_rejected(self):
        output={'coverage':[{'evidence_id':'E1','route':'no_change','order_numbers':[],'reason':'greeting'}],
                'facts':[{'evidence_ids':['E2']}],'uncertainties':[],'proposed_updates':[]}
        with self.assertRaises(ValueError):q.validate_output(output,{'E1'})
    def test_invalidated_result_cannot_create_candidates(self):
        _,tid=self.seed();number=q.claim(self.db,tid)
        with self.db:q.put_evidence(self.db,item('r2'),VERIFIED)
        q.finish(self.db,tid,number,output={'coverage':[],'uncertainties':[{'question':'Q'}],'proposed_updates':[]})
        self.assertEqual(self.db.execute('SELECT count(*) FROM candidates').fetchone()[0],0)
    def test_concurrent_claim_rejected(self):
        _,tid=self.seed()
        self.assertEqual(q.claim(self.db,tid),1)
        self.assertIsNone(q.claim(self.db,tid))
    def test_old_no_change_questions_not_actionable(self):
        output={'coverage':[{'evidence_id':'E1','route':'no_change'}],'proposed_updates':[]}
        self.assertEqual(q.question_state(output,{'evidence_ids':['E1']}),'historical_context_only')
    def test_real_routing_question_still_actionable(self):
        output={'coverage':[{'evidence_id':'E1','route':'uncertain'}],'proposed_updates':[]}
        self.assertEqual(q.question_state(output,{'evidence_ids':['E1']}),'candidate_only')
    def test_unknown_business_intake_queues_once(self):
        value=item();value.update(channel='whatsapp',direction='inbound',external_identity='123@s.whatsapp.net',text='Price list for 7 PCBA projects please')
        with self.db:
            q.put_evidence(self.db,value,{'status':'unverified','person_id':None})
            self.assertEqual(q.create_whatsapp_intake_tasks(self.db,'rules','model'),1)
            self.assertEqual(q.create_whatsapp_intake_tasks(self.db,'rules','model'),0)
        self.assertTrue(self.db.execute('SELECT person_id FROM analysis_tasks').fetchone()[0].startswith('unmatched-whatsapp:'))
    def test_greetings_and_seller_template_not_intake(self):
        value=item();value.update(channel='whatsapp',direction='outbound',external_identity='123@s.whatsapp.net',text='Please send model and quantity for our price')
        with self.db:
            q.put_evidence(self.db,value,{'status':'unverified','person_id':None})
            self.assertEqual(q.create_whatsapp_intake_tasks(self.db,'rules','model'),0)
    def test_protocol_edit_with_missing_original(self):
        key={'id':'target','remoteJid':'123@s.whatsapp.net','fromMe':False}
        original=q.encode({'key':dict(key,id='event'),'message':{'protocolMessage':{'type':14,'key':key,'editedMessage':{'extendedTextMessage':{'text':'Pause the samples'}},'timestampMs':{'high':417,'low':608160584}}}})
        effect=q.protocol_effect(original)
        self.assertEqual(effect['text'],'Pause the samples')
        self.assertEqual(effect['direction'],'inbound')
        self.assertIsNotNone(effect['timestamp'])
    def test_cross_chat_protocol_rejected(self):
        original=q.encode({'key':{'remoteJid':'123@s.whatsapp.net'},'message':{'protocolMessage':{'type':14,'key':{'id':'target','fromMe':False,'remoteJid':'456@s.whatsapp.net'}}}})
        self.assertIsNone(q.protocol_effect(original))
    def test_null_unknown_is_not_cited_fact(self):
        raw={'facts':[{'type':'country','value':None,'evidence_ids':[]},{'type':'qty','value':2,'evidence_ids':['M01']}],
             'coverage':[{'evidence_id':'M01','route':'uncertain','order_numbers':[],'reason':'quantity'}],
             'uncertainties':[],'proposed_updates':[]}
        normalized=q.separate_unknown_fields(raw)
        q.validate_output(normalized,{'M01'})
        self.assertEqual(len(normalized['facts']),1)
        self.assertIsNone(normalized['unknown_fields'][0]['value'])
        self.assertEqual(len(raw['facts']),2)
    def test_non_null_uncited_fact_still_rejected(self):
        raw={'facts':[{'type':'country','value':'invented','evidence_ids':[]}],
             'coverage':[{'evidence_id':'M01','route':'uncertain','order_numbers':[],'reason':'X'}],
             'uncertainties':[],'proposed_updates':[]}
        with self.assertRaises(ValueError):q.validate_output(q.separate_unknown_fields(raw),{'M01'})

if __name__=='__main__': unittest.main()
