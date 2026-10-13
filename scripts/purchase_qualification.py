"""R02 qualification over individually evidenced, procurement-scoped facts.

No text inference, model calls or CRM writes. Model-produced values alone do not
pass this gate: a trusted adapter must attest their semantic support first.
"""
import decimal
import json
from signal_queue import digest,now

def check_fact(fact, person_id, opportunity_id, evidence):
    if not isinstance(fact,dict) or fact.get('person_id')!=person_id:return False
    if fact.get('opportunity_id')!=opportunity_id:return False
    if fact.get('support_status')!='verified_semantic_support' or not fact.get('value'):return False
    refs=fact.get('references',[])
    if not refs:return False
    for ref in refs:
        row=evidence.get(ref.get('id'))
        if not row or not row['active'] or row['person_id']!=person_id or row['revision']!=ref.get('revision'):return False
        quote=ref.get('quote')
        if not isinstance(quote,str) or not quote or quote not in row['text']:return False
    return True

def evaluate(purchase, evidence, customer):
    person_id=purchase['person_id'];opportunity_id=purchase['opportunity_id']
    facts=purchase.get('facts',{})
    valid={k:v for k,v in facts.items() if check_fact(v,person_id,opportunity_id,evidence)}
    missing=[]
    if 'product_model' not in valid:missing.append('产品型号或版本')
    quantity=valid.get('quantity',{})
    quantity_ok=False
    try:
        value=decimal.Decimal(str(quantity.get('value')))
        quantity_ok=(value.is_finite() and value>0 and quantity.get('unit') and quantity.get('scope')=='this_purchase' and
                     (not purchase.get('multi_project') or quantity.get('per_project_breakdown_verified') is True))
    except decimal.InvalidOperation:pass
    if not quantity_ok:missing.append('本次采购数量（多项目需对应具体项目）')
    # Owner-verified country can supply R02 destination as explicitly agreed.
    country_ok=(customer.get('person_id')==person_id and customer.get('country') and
                customer.get('country_verification')=='human_confirmation')
    if not ('destination' in valid or country_ok):missing.append('国家或本次收货地点')
    status=valid.get('procurement_status',{}).get('value')
    paused=status in ('paused','cancelled')
    current=purchase['current_stage']
    if missing:outcome='missing_requirements'
    elif paused:outcome='paused_or_cancelled'
    elif current!='询盘':outcome='preserve_current_stage'
    elif status!='active':outcome='activity_not_verified'
    else:outcome='eligible_needs_confirmed'
    return {'person_id':person_id,'opportunity_id':opportunity_id,'rule_id':'R02',
            'outcome':outcome,'missing_fields':missing,'paused_or_cancelled':paused,
            'current_stage':current,'proposed_stage':'需求确认' if outcome=='eligible_needs_confirmed' else None,
            'fact_snapshot_digest':digest(purchase),'checked_at':now(),
            'crm_writes':0,'model_calls':0}

def validate_store(store):
    if store.get('schema_version')!=1:raise ValueError('fact_store_version')
    ids=[p['opportunity_id'] for p in store.get('purchases',[])]
    if len(ids)!=len(set(ids)):raise ValueError('duplicate_purchase_context')

def evaluate_all(store,evidence,customers):
    validate_store(store)
    return [evaluate(p,evidence,customers.get(p['person_id'],{})) for p in store['purchases']]
