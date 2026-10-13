"""Create-only approved intake executor. No existing-record updates or order APIs."""
import json
import sqlite3
import urllib.request
import urllib.error
import uuid
from contextlib import closing
from signal_queue import ROOT,DATA,WORKSPACE,digest,encode,now,prospect_context

class PlanConflict(Exception):pass

ALLOWED={
 'people':{'id','name','craCountry','craSource','craWhatsappIdentity','craChatSummary'},
 'opportunities':{'id','name','pointOfContactId','stage','craPurchaseStage','craFulfilmentStatus','craChatSummary'},
}

def validate_plan(plan):
    unsigned={k:v for k,v in plan.items() if k!='plan_digest'}
    if plan.get('workspace_id')!=WORKSPACE or plan.get('plan_digest')!=digest(unsigned):raise PlanConflict('plan_digest')
    operations=plan.get('operations',[])
    if len(operations)!=3 or [o['collection'] for o in operations]!=['people','opportunities','opportunities']:raise PlanConflict('operation_scope')
    person=operations[0]
    for op in operations:
        uuid.UUID(op['id'])
        if op['body']['id']!=op['id'] or not set(op['body']).issubset(ALLOWED[op['collection']]):raise PlanConflict('field_scope')
        if op['collection']=='opportunities' and (op['body']['stage']!='NEW' or op['body']['craPurchaseStage']!='询盘' or op['body']['pointOfContactId']!=person['id']):raise PlanConflict('stage_or_relation')
    if len({o['id'] for o in operations})!=3:raise PlanConflict('duplicate_target')

def ensure_current(plan):
    validate_plan(plan)
    if plan['rules_hash']!=digest((ROOT/'crm-foundation/chat-signal-rules.md').read_text(encoding='utf-8')):raise PlanConflict('rules_changed')
    if plan['context_hash']!=digest(prospect_context(plan['operations'][0]['body']['craWhatsappIdentity'])):raise PlanConflict('context_changed')
    with closing(sqlite3.connect('file:'+str(DATA/'signal.sqlite3')+'?mode=ro',uri=True)) as db:
        for identifier in plan['evidence_ids']:
            if not db.execute('SELECT 1 FROM evidence WHERE id=? AND active=1',(identifier,)).fetchone():raise PlanConflict('source_changed')
        state=db.execute('SELECT state FROM analysis_tasks WHERE id=?',(plan['task_id'],)).fetchone()
        if not state or state[0] not in ('succeeded','succeeded_local_validation'):raise PlanConflict('task_changed')

def matches(record,body):
    return record is not None and all(record.get(key)==value for key,value in body.items()) and not record.get('deletedAt')

def apply_operations(plan,remote,save_checkpoint,guard=lambda:None):
    """Stable supplied IDs allow recovery; an existing different record is never patched."""
    validate_plan(plan)
    for op in plan['operations']:
        guard()
        current=remote.read(op['collection'],op['id'])
        if current is not None:
            if not matches(current,op['body']):raise PlanConflict('remote_record_differs')
        else:
            guard()
            try:remote.create(op['collection'],op['body'])
            except Exception:
                # A timed-out POST may have committed. Re-read the same fixed ID.
                current=remote.read(op['collection'],op['id'])
                if current is None:raise
            current=remote.read(op['collection'],op['id'])
            if not matches(current,op['body']):raise PlanConflict('readback_differs')
        save_checkpoint(op['id'],current)

class Remote:
    def __init__(self,token):self.token=token
    def call(self,method,path,body=None):
        req=urllib.request.Request('http://127.0.0.1:3000/rest/'+path,data=encode(body).encode() if body is not None else None,method=method,headers={'Authorization':'Bearer '+self.token,'Content-Type':'application/json'})
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req,timeout=15) as response:return json.load(response)
    def read(self,collection,identifier):
        try:result=self.call('GET',collection+'/'+identifier)
        except urllib.error.HTTPError as exc:
            if exc.code==404:return None
            raise
        # Twenty REST wraps the singular record in data.{person|opportunity}.
        singular={'people':'person','opportunities':'opportunity'}[collection]
        data=result.get('data',{})
        value=data.get(singular)
        if not isinstance(value,dict):raise PlanConflict('unexpected_api_response')
        return value
    def create(self,collection,body):return self.call('POST',collection,body)

def queue_schema(db):
    db.executescript('''CREATE TABLE IF NOT EXISTS crm_intake_outbox(
      request_id TEXT PRIMARY KEY,plan TEXT NOT NULL,state TEXT NOT NULL,attempts INTEGER NOT NULL DEFAULT 0,
      generation INTEGER NOT NULL DEFAULT 0,lease_until TEXT,error_code TEXT,updated_at TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS crm_intake_readback(request_id TEXT,record_id TEXT,payload TEXT,checked_at TEXT,
      PRIMARY KEY(request_id,record_id));''')

def read_config():
    return dict(line.split('=',1) for line in (ROOT/'deployment/review/.env').read_text(encoding='utf-8-sig').splitlines() if '=' in line and not line.startswith('#'))

def enabled():
    cfg=read_config()
    return cfg.get('CRA_CRM_INTAKE_ENABLED')=='true' and bool(cfg.get('CRA_CRM_INTAKE_API_KEY'))

def run():
    config=read_config()
    if config.get('CRA_CRM_INTAKE_ENABLED')!='true' or not config.get('CRA_CRM_INTAKE_API_KEY'):
        print('CRM intake executor disabled; no API calls.');return
    # Execution must be invoked after authorization and only for approved exact plans.
    with closing(sqlite3.connect(DATA/'review.sqlite3',timeout=20)) as db:
        db.row_factory=sqlite3.Row;queue_schema(db)
        approved=db.execute("SELECT * FROM requests WHERE status='approved'").fetchall()
        with db:
            for row in approved:
                payload=json.loads(row['payload']);plan=payload.get('executionPlan')
                if not plan or json.loads(row['decision'])['selectedChoiceId']!='create_intake':continue
                db.execute('INSERT OR IGNORE INTO crm_intake_outbox(request_id,plan,state,updated_at) VALUES(?,?,?,?)',(row['id'],encode(plan),'pending',now()))
        import datetime as dt
        db.execute('BEGIN IMMEDIATE')
        current=now()
        task=db.execute("SELECT * FROM crm_intake_outbox WHERE attempts<3 AND ((state='pending' AND (lease_until IS NULL OR lease_until<?)) OR (state='running' AND lease_until<?)) ORDER BY updated_at LIMIT 1",(current,current)).fetchone()
        if not task:db.commit();return
        generation=task['generation']+1
        lease=(dt.datetime.now(dt.timezone.utc)+dt.timedelta(minutes=5)).isoformat()
        db.execute("UPDATE crm_intake_outbox SET state='running',generation=?,attempts=attempts+1,lease_until=?,updated_at=? WHERE request_id=?",(generation,lease,current,task['request_id']));db.commit()
        identifier=task['request_id'];plan=json.loads(task['plan'])
        def checkpoint(record_id,record):
            with db:
                updated=db.execute("UPDATE crm_intake_outbox SET updated_at=? WHERE request_id=? AND generation=? AND state='running'",(now(),identifier,generation))
                if updated.rowcount!=1:raise PlanConflict('stale_executor')
                db.execute('INSERT OR REPLACE INTO crm_intake_readback VALUES(?,?,?,?)',(identifier,record_id,encode(record),now()))
        try:
            def guard():
                ensure_current(plan)
                if db.execute('SELECT status FROM requests WHERE id=?',(identifier,)).fetchone()[0]!='approved':raise PlanConflict('approval_invalidated')
                owner=db.execute('SELECT generation,state FROM crm_intake_outbox WHERE request_id=?',(identifier,)).fetchone()
                if owner['generation']!=generation or owner['state']!='running':raise PlanConflict('stale_executor')
            guard()
            apply_operations(plan,Remote(config['CRA_CRM_INTAKE_API_KEY']),checkpoint,guard)
            state='succeeded';error=None
        except PlanConflict as exc:state='conflict';error=str(exc)
        except Exception as exc:
            transient=isinstance(exc,(TimeoutError,urllib.error.URLError)) and (not isinstance(exc,urllib.error.HTTPError) or exc.code==429 or exc.code>=500)
            state='pending' if transient and task['attempts']+1<3 else 'failed';error=type(exc).__name__
        retry_at=(dt.datetime.now(dt.timezone.utc)+dt.timedelta(minutes=2**(task['attempts']+1))).isoformat() if state=='pending' else None
        with db:db.execute('UPDATE crm_intake_outbox SET state=?,error_code=?,lease_until=?,updated_at=? WHERE request_id=? AND generation=?',(state,error,retry_at,now(),identifier,generation))
        print('CRM intake execution:',state)

if __name__=='__main__':run()
