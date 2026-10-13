"""Incremental R02 runner: known procurement only, model candidates are not writes."""
import json
import sqlite3
from contextlib import closing
import signal_queue as q
from crm_intake_executor import Remote,read_config
from crm_update_executor import schema,run as execute_updates
from r02_signal_adapter import verified_inputs,stage_plan,authorize_plan

POLICY=q.ROOT/'deployment/review/r02-policy.json'

def policy():return json.loads(POLICY.read_text(encoding='utf-8')) if POLICY.exists() else {'enabled':False}

def inputs(person_id):
    store=json.loads((q.DATA/'purchase-facts.json').read_text(encoding='utf-8'))
    with closing(q.connect()) as db:
        evidence={r['id']:dict(r) for r in db.execute('SELECT * FROM evidence WHERE person_id=? AND active=1',(person_id,))}
    remote=Remote(read_config()['CRA_CRM_INTAKE_API_KEY']);person=remote.read('people',person_id)
    background=q.prospect_context(person.get('craWhatsappIdentity',''))
    customer={'person_id':person_id,'country':background['country'],'country_verification':'human_confirmation'} if background and background['country']==person.get('craCountry') else {}
    return store,evidence,customer,remote

def authorize_current(plan):
    settings=policy()
    if not settings.get('enabled') or plan['person_id'] not in settings['person_ids'] or plan.get('policy_digest')!=q.digest(settings):return False
    with closing(q.connect()) as db:q.sync(db)
    store,evidence,customer,_=inputs(plan['person_id'])
    return authorize_plan(plan,evidence,store,customer)

def deterministic_finish(db,task,rows):
    """Record complete supported coverage, with zero AI attempts and no invented facts."""
    result={'coverage':[{'evidence_id':r['id'],'route':'customer_only','order_numbers':[],
                       'reason':'明确采购续接，R02适配器核验'} for r in rows],
            'facts':[],'uncertainties':[],'proposed_updates':[],'analysis_source':'deterministic_r02_v1'}
    with db:
        changed=db.execute("UPDATE analysis_tasks SET state='succeeded',result=?,finished_at=?,error_code=NULL WHERE id=? AND state='pending' AND attempts=0",(q.encode(result),q.now(),task['id'])).rowcount
    return bool(changed)

def run():
    settings=policy();status={'status':'ok','checked_at':q.now(),'new_stage_plans':0,'model_calls':0,'crm_stage_writes_verified':0}
    if not settings.get('enabled'):return
    with closing(q.connect()) as db:
        status['sync']=q.sync(db)
        pending=db.execute("SELECT * FROM analysis_tasks WHERE state IN ('pending','awaiting_retry') AND attempts<3 ORDER BY started_at,id").fetchall()
        for task in pending:
            if task['person_id'] not in settings['person_ids']:continue
            store,evidence,customer,remote=inputs(task['person_id'])
            purchases=[p for p in store['purchases'] if p['person_id']==task['person_id']]
            current={p['opportunity_id']:remote.read('opportunities',p['opportunity_id']) for p in purchases}
            context_path=q.DATA/'crm-contexts.json'
            if context_path.exists():
                contexts=json.loads(context_path.read_text(encoding='utf-8'))
                for context in contexts['customers']:
                    if context['person_id']!=task['person_id']:continue
                    for purchase_context in context['purchase_contexts']:
                        record=current.get(purchase_context['opportunity_id'])
                        if record:
                            for key in list(purchase_context['crm_fields']):purchase_context['crm_fields'][key]=record.get(key)
                    context['snapshot_at']=q.now()
                tmp=context_path.with_suffix('.json.tmp');tmp.write_text(json.dumps(contexts,ensure_ascii=False,indent=2),encoding='utf-8');tmp.replace(context_path)
            # Human changes and completed R02 cannot be silently reset to inquiry.
            usable=[p for p in purchases if current[p['opportunity_id']].get('pointOfContactId')==task['person_id'] and
                    current[p['opportunity_id']].get('craPurchaseStage')==p['current_stage']=='询盘']
            rows=[dict(r) for r in db.execute('SELECT e.* FROM evidence e JOIN task_evidence t ON t.evidence_id=e.id WHERE t.task_id=? ORDER BY occurred_at,e.id',(task['id'],))]
            candidates=[verified_inputs(r,usable,customer,evidence) for r in rows]
            if rows and all(c and c['qualification']['proposed_stage']=='需求确认' for c in candidates) and task['state']=='pending' and task['attempts']==0:
                if not deterministic_finish(db,task,rows):continue
            else:
                # Official DeepSeek scope: this known customer's new procurement
                # text plus needed context. Attempt accounting remains q.analyze.
                if not q.config().get('MODEL_BUSINESS_DATA_ENABLED')=='true':continue
                result=q.analyze(db,task['id']);status['model_calls']+=int(result.get('status')!='not_claimed')
                if result.get('status')!='succeeded':break
            for row,candidate in zip(rows,candidates):
                if not candidate:continue
                plan=stage_plan(candidate,current[candidate['purchase']['opportunity_id']],task,task['rules_hash'])
                if not plan:continue
                plan['base_purchase']=next(p for p in usable if p['opportunity_id']==plan['record_id'])
                plan['policy_digest']=q.digest(settings)
                plan['plan_digest']=q.digest({k:v for k,v in plan.items() if k!='plan_digest'})
                identifier='r02:'+q.digest([plan['person_id'],plan['record_id'],row['id'],row['revision'],'需求确认'])
                if not authorize_current(plan):continue
                with closing(sqlite3.connect(q.DATA/'review.sqlite3',timeout=20)) as review:
                    schema(review)
                    with review:
                        old=review.execute('SELECT plan FROM crm_update_outbox WHERE request_id=?',(identifier,)).fetchone()
                        if old and json.loads(old[0])!=plan:continue
                        status['new_stage_plans']+=review.execute('INSERT OR IGNORE INTO crm_update_outbox(request_id,plan,state,updated_at) VALUES(?,?,?,?)',(identifier,q.encode(plan),'pending',q.now())).rowcount
                        review.execute('CREATE TABLE IF NOT EXISTS r02_execution_audit(request_id TEXT PRIMARY KEY,policy_digest TEXT,source_task_id TEXT,plan_digest TEXT,created_at TEXT)')
                        review.execute('INSERT OR IGNORE INTO r02_execution_audit VALUES(?,?,?,?,?)',(identifier,plan['policy_digest'],task['id'],plan['plan_digest'],q.now()))
                        # Clearly labeled automatic history; never impersonates
                        # the owner or fabricates a human approval audit.
                        item={'id':identifier,'workspaceId':q.WORKSPACE,'planDigest':plan['plan_digest'],'reviewFormatVersion':3,
                            'ruleId':'R02','ruleVersion':plan['rules_hash'],'title':'规则自动更新：商机进入需求确认',
                            'reason':'已确认R02规则内的明确客户采购续接；程序核对型号、数量、国家及商机归属。此项为自动执行历史，不是人工审批。',
                            'status':'approved','createdAt':plan['created_at'],'target':{'objectLabel':'商机','recordLabel':current[plan['record_id']]['name']},
                            'changes':[{'fieldLabel':'采购阶段','before':'询盘','after':'需求确认'}],
                            'evidence':[{'sourceLabel':row['channel']+' · 客户发来','reference':row['id'],'excerpt':row['text']}],
                            'choices':[],'contextUpdatePlan':plan,'execution':{'status':'not_started','message':'待执行'},'canDecide':False}
                        decision={'outcome':'approved','actorLabel':'R02规则自动判定（非人工审批）','decidedAt':q.now(),'note':'按经营者已确认规则执行','selectedChoiceId':None}
                        review.execute('INSERT OR IGNORE INTO requests VALUES(?,?,?,?,?,?,?,?)',(identifier,task['id'],task['rules_hash'],q.digest(None),q.encode(item),'approved',plan['created_at'],q.encode(decision)))
            # One new customer analysis unit per minute; never reprocess history.
            break
    execute_updates()
    with closing(sqlite3.connect(q.DATA/'review.sqlite3')) as review:
        schema(review)
        status['crm_stage_writes_verified']=review.execute("SELECT count(*) FROM crm_update_outbox WHERE request_id LIKE 'r02:%' AND state='succeeded'").fetchone()[0]
    (q.DATA/'r02-runtime-status.json').write_text(json.dumps(status,ensure_ascii=False,indent=2),encoding='utf-8')
    return status

if __name__=='__main__':
    try:run()
    except Exception as exc:
        (q.DATA/'r02-runtime-status.json').write_text(json.dumps({'status':'failed','error_type':type(exc).__name__,'checked_at':q.now()}),encoding='utf-8')
        raise
