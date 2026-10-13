"""Bounded approved context updates through Twenty's atomic filtered REST mutation."""
import json
import sqlite3
import urllib.parse
import urllib.error
import uuid
import datetime as dt
from contextlib import closing
from crm_intake_executor import Remote,read_config,PlanConflict
from signal_queue import ROOT,DATA,WORKSPACE,digest,encode,now,prospect_context
from chat_identity import resolve

FIELDS={'people':{'craChatSummary'},'opportunities':{'craChatSummary'}}

def schema(db):
    db.executescript('''CREATE TABLE IF NOT EXISTS crm_update_outbox(
      request_id TEXT PRIMARY KEY,plan TEXT,state TEXT,attempts INTEGER DEFAULT 0,
      generation INTEGER DEFAULT 0,lease_until TEXT,error_code TEXT,updated_at TEXT);
      CREATE TABLE IF NOT EXISTS crm_update_readback(request_id TEXT PRIMARY KEY,payload TEXT,checked_at TEXT);''')

def validate(plan):
    if plan.get('workspace_id')!=WORKSPACE or plan.get('plan_digest')!=digest({k:v for k,v in plan.items() if k!='plan_digest'}):raise PlanConflict('update_plan_digest')
    uuid.UUID(plan['record_id']);uuid.UUID(plan['person_id'])
    collection=plan['collection'];fields=plan['after']
    stage_plan=plan.get('kind')=='r02_explicit_stage'
    allowed={'craPurchaseStage'} if stage_plan and collection=='opportunities' else FIELDS.get(collection,set())
    if collection not in FIELDS or not fields or not set(fields)<=allowed or set(plan['before'])!=set(fields):raise PlanConflict('update_field_scope')
    if stage_plan and (plan['before']!={'craPurchaseStage':'询盘'} or fields!={'craPurchaseStage':'需求确认'} or not plan.get('purchase_facts')):raise PlanConflict('r02_stage_scope')
    if any(not isinstance(v,str) or len(v)>6000 for v in fields.values()):raise PlanConflict('update_value_type')
    if not plan.get('expected_updated_at') or not plan.get('evidence_ids') or not plan.get('task_id'):raise PlanConflict('update_provenance_required')
    if collection=='people' and plan['person_id']!=plan['record_id']:raise PlanConflict('person_scope')

def ensure_current(plan):
    validate(plan)
    if plan['rules_hash']!=digest((ROOT/'crm-foundation/chat-signal-rules.md').read_text(encoding='utf-8')):raise PlanConflict('rules_changed')
    with closing(sqlite3.connect('file:'+(DATA/'signal.sqlite3').as_posix()+'?mode=ro',uri=True)) as db:
        for eid in plan['evidence_ids']:
            row=db.execute('SELECT active,person_id,channel,external_identity FROM evidence WHERE id=?',(eid,)).fetchone()
            if not row or row[:2]!=(1,plan['person_id']) or resolve(row[2],row[3])['person_id']!=plan['person_id']:raise PlanConflict('source_changed')
            if plan.get('context_hash') and digest(prospect_context(row[3]) if row[2]=='whatsapp' else None)!=plan['context_hash']:raise PlanConflict('owner_context_changed')
        task=db.execute('SELECT state FROM analysis_tasks WHERE id=?',(plan['task_id'],)).fetchone()
        if not task or task[0] not in ('succeeded','succeeded_local_validation'):raise PlanConflict('analysis_changed')

class UpdateRemote(Remote):
    def conditional_update(self,plan):
        # Only the immutable ID and expected remote version can enter the filter.
        uuid.UUID(plan['record_id'])
        timestamp=plan['expected_updated_at']
        dt.datetime.fromisoformat(timestamp.replace('Z','+00:00'))
        expression='and(id[eq]:'+plan['record_id']+',updatedAt[eq]:'+timestamp+')'
        result=self.call('PATCH',plan['collection']+'?'+urllib.parse.urlencode({'filter':expression}),plan['after'])
        values=result.get('data',{}).get('update'+plan['collection'][0].upper()+plan['collection'][1:])
        if not isinstance(values,list) or len(values)>1:raise PlanConflict('unexpected_update_response')
        if not values:raise PlanConflict('remote_version_conflict')
        return values[0]

def agrees(record,fields):return record is not None and not record.get('deletedAt') and all(record.get(k)==v for k,v in fields.items())

def execute(plan,remote,guard):
    validate(plan);guard()
    current=remote.read(plan['collection'],plan['record_id'])
    if not current or current.get('deletedAt'):raise PlanConflict('remote_record_missing')
    if plan['collection']=='opportunities' and current.get('pointOfContactId')!=plan['person_id']:raise PlanConflict('remote_relation_changed')
    # Desired value is already present (including recovery after a lost response).
    if agrees(current,plan['after']):return {'record':current,'action':'already_satisfied'}
    if current.get('updatedAt')!=plan['expected_updated_at'] or not agrees(current,plan['before']):raise PlanConflict('remote_version_conflict')
    guard()
    try:remote.conditional_update(plan)
    except (TimeoutError,OSError,urllib.error.URLError):
        current=remote.read(plan['collection'],plan['record_id'])
        if agrees(current,plan['after']):return {'record':current,'action':'recovered_readback'}
        raise
    current=remote.read(plan['collection'],plan['record_id'])
    if not agrees(current,plan['after']):raise PlanConflict('update_readback_differs')
    return {'record':current,'action':'updated'}

def run():
    cfg=read_config()
    if cfg.get('CRA_CRM_INTAKE_ENABLED')!='true':return
    with closing(sqlite3.connect(DATA/'review.sqlite3',timeout=20)) as db:
        db.row_factory=sqlite3.Row;schema(db)
        current_time=now();db.execute('BEGIN IMMEDIATE')
        row=db.execute("SELECT * FROM crm_update_outbox WHERE attempts<3 AND ((state='pending' AND (lease_until IS NULL OR lease_until<?)) OR (state='running' AND lease_until<?)) ORDER BY updated_at LIMIT 1",(current_time,current_time)).fetchone()
        if not row:db.commit();return
        generation=row['generation']+1
        lease=(dt.datetime.now(dt.timezone.utc)+dt.timedelta(minutes=5)).isoformat()
        db.execute("UPDATE crm_update_outbox SET state='running',attempts=attempts+1,generation=?,lease_until=? WHERE request_id=?",(generation,lease,row['request_id']));db.commit()
        plan=json.loads(row['plan'])
        def guard():
            ensure_current(plan)
            if plan.get('kind')=='r02_explicit_stage':
                from r02_runtime import authorize_current
                if not authorize_current(plan):raise PlanConflict('r02_policy_or_facts_changed')
                ensure_current(plan)
                lease=db.execute('SELECT state,generation,plan FROM crm_update_outbox WHERE request_id=?',(row['request_id'],)).fetchone()
                if not lease or lease['state']!='running' or lease['generation']!=generation or json.loads(lease['plan'])!=plan:raise PlanConflict('stale_update_executor')
                return
            live=db.execute('SELECT r.status,r.decision,r.payload,o.state,o.generation FROM requests r JOIN crm_update_outbox o ON r.id=o.request_id WHERE r.id=?',(row['request_id'],)).fetchone()
            if not live or live['status']!='approved' or json.loads(live['decision'])['selectedChoiceId']!='update_context' or json.loads(live['payload']).get('contextUpdatePlan')!=plan or live['state']!='running' or live['generation']!=generation:raise PlanConflict('update_approval_or_lease_changed')
        try:
            result=execute(plan,UpdateRemote(cfg['CRA_CRM_INTAKE_API_KEY']),guard)
            guard()
            if plan.get('kind')=='r02_explicit_stage':
                facts_path=DATA/'purchase-facts.json';facts=json.loads(facts_path.read_text(encoding='utf-8'))
                facts['purchases']=[dict(plan['purchase_facts'],current_stage='需求确认') if p['opportunity_id']==plan['record_id'] else p for p in facts['purchases']]
                temp=facts_path.with_suffix('.json.tmp');temp.write_text(json.dumps(facts,ensure_ascii=False,indent=2),encoding='utf-8');temp.replace(facts_path)
            context_path=DATA/'crm-contexts.json'
            if context_path.exists():
                contexts=json.loads(context_path.read_text(encoding='utf-8'))
                for context in contexts['customers']:
                    if context['person_id']!=plan['person_id']:continue
                    target=context['person'] if plan['collection']=='people' else next((c['crm_fields'] for c in context['purchase_contexts'] if c['opportunity_id']==plan['record_id']),None)
                    if target is not None:
                        for key in list(target):target[key]=result['record'].get(key)
                        context['snapshot_at']=now()
                temporary=context_path.with_suffix('.json.tmp')
                temporary.write_text(json.dumps(contexts,ensure_ascii=False,indent=2),encoding='utf-8');temporary.replace(context_path)
            with db:
                changed=db.execute("UPDATE crm_update_outbox SET state='succeeded',error_code=NULL,lease_until=NULL,updated_at=? WHERE request_id=? AND generation=? AND state='running'",(now(),row['request_id'],generation)).rowcount
                if changed!=1:raise PlanConflict('stale_update_executor')
                db.execute('INSERT OR REPLACE INTO crm_update_readback VALUES(?,?,?)',(row['request_id'],encode(result),now()))
        except Exception as exc:
            retryable=isinstance(exc,(TimeoutError,OSError,urllib.error.URLError)) and not isinstance(exc,PlanConflict)
            if isinstance(exc,urllib.error.HTTPError):retryable=exc.code==429 or exc.code>=500
            state='pending' if retryable and row['attempts']+1<3 else 'conflict' if isinstance(exc,PlanConflict) else 'failed'
            code=str(exc) if isinstance(exc,PlanConflict) else type(exc).__name__
            delay=(dt.datetime.now(dt.timezone.utc)+dt.timedelta(minutes=2**(row['attempts']+1))).isoformat() if state=='pending' else None
            with db:db.execute('UPDATE crm_update_outbox SET state=?,error_code=?,lease_until=?,updated_at=? WHERE request_id=? AND generation=?',(state,code,delay,now(),row['request_id'],generation))

if __name__=='__main__':run()
