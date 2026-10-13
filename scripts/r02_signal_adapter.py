"""Conservative R02 adapter for explicit new buyer procurement statements.

Unsupported language/expressions remain candidates. No inference from a number
alone, and no model self-attestation. Never writes orders or sends messages.
"""
import re
import datetime as dt
from purchase_qualification import evaluate,check_fact
from signal_queue import digest,now

def timestamp(value):
    try:return dt.datetime.fromisoformat(value.replace('Z','+00:00'))
    except (AttributeError,ValueError):return None

def extract(row,purchase,customer):
    if not row['active'] or row['direction']!='inbound' or row['person_id']!=purchase['person_id'] or row['completeness'] not in ('text_only','text','text_available','edited_text'):
        return None
    old=purchase.get('facts',{}).get('product_model')
    if not old or old.get('support_status')!='verified_semantic_support':return None
    model=old['value'];text=row['text'].strip()
    if purchase.get('multi_project'):return None
    # Full-message templates intentionally cannot swallow negation, conditions,
    # questions, future forecasts, competing requests, or quoted mail history.
    patterns=[
      r'Please proceed with (?P<qty>[1-9][0-9]*(?:,[0-9]{3})*) (?:pcs|pieces|units) of '+re.escape(model)+r'(?: for delivery to (?P<country>[A-Za-z ]+))?[.!]?',
      r'请继续采购\s*'+re.escape(model)+r'[，,]\s*数量\s*(?P<qty>[1-9][0-9]*(?:,[0-9]{3})*)\s*件[。.]?']
    match=next((m for p in patterns if (m:=re.fullmatch(p,text,re.IGNORECASE))),None)
    if not match:return None
    raw=match.group('qty')
    if ',' in raw and not re.fullmatch(r'[1-9][0-9]{0,2}(?:,[0-9]{3})+',raw):return None
    new_time=timestamp(row['occurred_at'])
    if not new_time or new_time.tzinfo is None:return None
    for fact in purchase.get('facts',{}).values():
        for ref in fact.get('references',[]):
            previous=timestamp(ref.get('occurred_at'))
            if previous and previous>=new_time:return None
    country=match.groupdict().get('country')
    if country and country.strip().casefold()!=str(customer.get('country','')).casefold():return None
    def fact(value,**extra):
        return dict(value=value,person_id=purchase['person_id'],opportunity_id=purchase['opportunity_id'],
            support_status='verified_semantic_support',support_source='r02_explicit_statement_v1',
            references=[{'id':row['id'],'revision':row['revision'],'quote':text,'occurred_at':row['occurred_at']}],**extra)
    proposed=dict(purchase,facts={'product_model':fact(model),'quantity':fact(raw.replace(',',''),unit='pcs',scope='this_purchase'),
                                 'procurement_status':fact('active')})
    result=evaluate(proposed,{row['id']:row},customer)
    return {'purchase':proposed,'qualification':result,'evidence_id':row['id']}

def choose(row,purchases,customer):
    found=[p for p in (extract(row,p,customer) for p in purchases) if p]
    return found[0] if len(found)==1 else None

def stage_plan(candidate,record,task,rules_hash):
    p=candidate['purchase'];result=candidate['qualification']
    if result['proposed_stage']!='需求确认' or record.get('pointOfContactId')!=p['person_id'] or record.get('craPurchaseStage')!='询盘':return None
    from signal_queue import WORKSPACE
    plan={'kind':'r02_explicit_stage','workspace_id':WORKSPACE,'collection':'opportunities','record_id':p['opportunity_id'],
        'person_id':p['person_id'],'expected_updated_at':record['updatedAt'],
        'before':{'craPurchaseStage':'询盘'},'after':{'craPurchaseStage':'需求确认'},
        'task_id':task['id'],'rules_hash':rules_hash,'evidence_ids':[candidate['evidence_id']],
        'purchase_facts':p,'created_at':now()}
    plan['plan_digest']=digest(plan)
    return plan

def verified_inputs(row,purchases,customer,evidence):
    row_time=timestamp(row.get('occurred_at')) if row else None
    if not row_time:return None
    # A newer message may pause/correct the request. Unsupported newer wording
    # cannot be silently ignored merely because an older statement was clear.
    if any(e.get('person_id')==row['person_id'] and e.get('active') and
           (e.get('text','').strip() or e.get('completeness')=='revision_event_unresolved') and
           timestamp(e.get('occurred_at')) and timestamp(e['occurred_at'])>row_time for e in evidence.values()):return None
    supported=[]
    for purchase in purchases:
        model=purchase.get('facts',{}).get('product_model')
        if not check_fact(model,purchase['person_id'],purchase['opportunity_id'],evidence):continue
        copy=dict(purchase,facts={k:dict(v,references=[dict(ref,occurred_at=evidence[ref['id']]['occurred_at'])
            for ref in v.get('references',[]) if ref.get('id') in evidence]) for k,v in purchase.get('facts',{}).items()})
        supported.append(copy)
    return choose(row,supported,customer)

def authorize_plan(plan,evidence,store,customer):
    current=next((p for p in store['purchases'] if p['opportunity_id']==plan['record_id'] and p['person_id']==plan['person_id']),None)
    validate_purchase=plan.get('base_purchase')
    applied=dict(plan['purchase_facts'],current_stage='需求确认')
    if not validate_purchase or current not in (validate_purchase,applied) or len(plan['evidence_ids'])!=1:return False
    row=evidence.get(plan['evidence_ids'][0])
    candidate=verified_inputs(row,[validate_purchase],customer,evidence) if row else None
    return bool(candidate and candidate['qualification']['proposed_stage']=='需求确认' and candidate['purchase']==plan['purchase_facts'])
