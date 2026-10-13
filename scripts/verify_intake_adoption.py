"""One bounded local adoption after fresh official REST readbacks; no model calls."""
import json
import pathlib
import sqlite3
from contextlib import closing
from crm_intake_executor import read_config, Remote, matches
from chat_identity import approved_intake, resolve
from adopt_intake_identity import adopt
import signal_queue as q

def run():
    plan=json.loads((q.DATA/'customer-intake-plan.json').read_text(encoding='utf-8'))
    with closing(sqlite3.connect(q.DATA/'review.sqlite3')) as review:
        review.row_factory=sqlite3.Row
        rows=review.execute("SELECT r.id,r.decision,o.state,o.attempts FROM requests r JOIN crm_intake_outbox o ON o.request_id=r.id WHERE r.status='approved' AND o.state='succeeded'").fetchall()
        rows=[r for r in rows if json.loads(review.execute('SELECT plan FROM crm_intake_outbox WHERE request_id=?',(r['id'],)).fetchone()[0])==plan]
        if len(rows)!=1:raise ValueError('exact_successful_review_required')
        request=dict(rows[0])
    op=plan['operations'][0]
    binding={'channel':'whatsapp','identity':op['body']['craWhatsappIdentity'],'person_id':op['id'],
        'display_name':op['body']['name']['firstName'],'active':True,
        'verification':{'source':'crm_review_approval','request_id':request['id']}}
    if not approved_intake(binding):raise ValueError('approval_proof_invalid')
    remote=Remote(read_config()['CRA_CRM_INTAKE_API_KEY'])
    records=[]
    for operation in plan['operations']:
        record=remote.read(operation['collection'],operation['id'])
        if not matches(record,operation['body']):raise ValueError('fresh_remote_readback_differs')
        records.append({k:record.get(k) for k in set(operation['body'])|{'updatedAt','createdAt'}})
    captured=q.now()
    snapshot={'person_id':op['id'],'snapshot_at':captured,'source':'official_twenty_rest_readback',
        'approval_request_id':request['id'],'person':records[0],
        'purchase_contexts':[{'opportunity_id':r['id'],'crm_fields':r,'source_task_id':plan['task_id'],
            'source_evidence_ids':plan['evidence_ids'],'evidence_scope':'shared intake evidence; per-fact support and procurement routing must be checked before updates'} for r in records[1:]],
        'known_orders':[]}
    context_path=q.DATA/'crm-contexts.json'
    contexts=json.loads(context_path.read_text(encoding='utf-8')) if context_path.exists() else {'customers':[]}
    contexts['customers']=[c for c in contexts['customers'] if c['person_id']!=op['id']]+[snapshot]
    identity_path=q.DATA/'identity-bindings.json'
    identities=json.loads(identity_path.read_text(encoding='utf-8'))
    existing=[b for b in identities['bindings'] if b['channel']=='whatsapp' and b['identity']==binding['identity'] and b.get('active')]
    if any(b!=binding for b in existing):raise ValueError('existing_binding_conflict')
    if not existing:identities['bindings'].append(binding)
    # Scheduled signal sync is temporarily stopped by the caller. Source adoption
    # is idempotent: a crash before binding file save is recoverable by rerunning.
    db=q.connect()
    try:
        db.execute('BEGIN IMMEDIATE')
        adopted=adopt(db,binding)
        context_path.write_text(json.dumps(contexts,ensure_ascii=False,indent=2),encoding='utf-8')
        identity_path.write_text(json.dumps(identities,ensure_ascii=False,indent=2),encoding='utf-8')
        resolved=resolve('whatsapp',binding['identity'])
        if resolved['person_id']!=op['id']:raise ValueError('resolved_identity_differs')
        db.commit()
        before=db.execute('SELECT count(*) FROM analysis_tasks').fetchone()[0]
        result=q.sync(db)
        after=db.execute('SELECT count(*) FROM analysis_tasks').fetchone()[0]
        source=dict(db.execute('SELECT id,state,attempts FROM analysis_tasks WHERE id=?',(plan['task_id'],)).fetchone())
        verification={'verified_at':captured,'request_id':request['id'],'execution_state':request['state'],
            'execution_attempts':request['attempts'],'fresh_remote_readbacks':3,'person_id':op['id'],
            'opportunity_ids':[r['id'] for r in records[1:]],'identity_status':resolved['status'],
            'historical_evidence_adopted':db.execute('SELECT count(*) FROM identity_adoptions WHERE request_id=?',(request['id'],)).fetchone()[0],
            'new_adoptions_this_run':adopted,'source_analysis_preserved':source,
            'task_count_before':before,'task_count_after':after,'sync_result':result,
            'model_calls_this_verification':0,'crm_writes_this_verification':0}
        (q.DATA/'intake-adoption-verification.json').write_text(json.dumps(verification,ensure_ascii=False,indent=2),encoding='utf-8')
        status_path=q.DATA/'intake-api-verification.json'
        status=json.loads(status_path.read_text(encoding='utf-8'))
        status.update(real_write_verified=True,planned_records_exist=[True]*3,
                      final_verification=verification)
        with closing(sqlite3.connect(q.DATA/'review.sqlite3')) as review:
            status['review_counts']=dict(review.execute('SELECT status,count(*) FROM requests GROUP BY status'))
            status['outbox_count']=review.execute('SELECT count(*) FROM crm_intake_outbox').fetchone()[0]
        status_path.write_text(json.dumps(status,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(verification,ensure_ascii=False))
    finally:db.close()

if __name__=='__main__':run()
