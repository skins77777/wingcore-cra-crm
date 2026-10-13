"""Evaluate the two executed intake topics with reviewed source interpretations.

This bounded adapter only reuses the verified intake plan; it does not approve
new model facts. New messages require their own semantic validation adapter.
"""
import json
from contextlib import closing
from chat_identity import approved_intake
from crm_intake_executor import Remote,read_config
from signal_queue import DATA,connect,prospect_context,now
from purchase_qualification import evaluate_all

def run():
    intake=json.loads((DATA/'customer-intake-plan.json').read_text(encoding='utf-8'))
    identity=intake['operations'][0]['body']['craWhatsappIdentity']
    bindings=json.loads((DATA/'identity-bindings.json').read_text(encoding='utf-8'))['bindings']
    matches=[b for b in bindings if b['channel']=='whatsapp' and b['identity']==identity and b.get('active')]
    if len(matches)!=1 or approved_intake(matches[0])!=intake:raise ValueError('executed_intake_proof_required')
    person_id=intake['operations'][0]['id'];sample_id=intake['operations'][1]['id'];pcba_id=intake['operations'][2]['id']
    remote=Remote(read_config()['CRA_CRM_INTAKE_API_KEY'])
    person=remote.read('people',person_id);sample=remote.read('opportunities',sample_id);pcba=remote.read('opportunities',pcba_id)
    if any(r.get('deletedAt') for r in (person,sample,pcba)) or sample['pointOfContactId']!=person_id or pcba['pointOfContactId']!=person_id:raise ValueError('current_crm_scope_changed')
    with closing(connect()) as db:
        evidence={r['id']:dict(r) for r in db.execute('SELECT * FROM evidence WHERE active=1 AND person_id=?',(person_id,))}
    def supported(value,opportunity,index,quote,**extra):
        eid=intake['evidence_ids'][index];row=evidence[eid]
        if quote not in row['text']:raise ValueError('intake_quote_changed')
        return dict(value=value,person_id=person_id,opportunity_id=opportunity,
            support_status='verified_semantic_support',support_source='reviewed_executed_intake_adapter_v1',
            references=[{'id':eid,'revision':row['revision'],'quote':quote}],**extra)
    # Interpretations already represented in the approved intake: two samples,
    # explicitly paused; 10,000 for an intended first order, not per-project units.
    facts={
        'product_model':supported('AI VISION CUBE DT Pro',sample_id,6,'AI VISION CUBE DT Pro'),
        'quantity':supported('2',sample_id,0,'По двум тестовым образцам пока что не надо',unit='pcs',scope='this_purchase'),
        'procurement_status':supported('paused',sample_id,0,'По двум тестовым образцам пока что не надо')}
    pcba_facts={'quantity':supported('10000',pcba_id,15,'For our first order, we are looking to purchase 10,000 units.',unit='pcs',scope='future_first_order',per_project_breakdown_verified=False)}
    store={'schema_version':1,'source_request_id':matches[0]['verification']['request_id'],
        'source_task_id':intake['task_id'],'captured_at':now(),'purchases':[
            {'person_id':person_id,'opportunity_id':sample_id,'current_stage':sample['craPurchaseStage'],'facts':facts},
            {'person_id':person_id,'opportunity_id':pcba_id,'current_stage':pcba['craPurchaseStage'],'multi_project':True,'facts':pcba_facts}]}
    background=prospect_context(identity)
    country=background['country'] if 'country' in background else background.get('country_en')
    # Country from this exact owner confirmation must also agree with current CRM.
    customer={'person_id':person_id,'country':country,'country_verification':'human_confirmation'} if country and person['craCountry']==country else {}
    results=evaluate_all(store,evidence,{person_id:customer})
    report={'checked_at':now(),'results':results,'crm_writes':0,'model_calls':0,
        'scope':'two executed intake topics only; new message fact extraction and stage writes are not enabled'}
    (DATA/'purchase-facts.json').write_text(json.dumps(store,ensure_ascii=False,indent=2),encoding='utf-8')
    (DATA/'qualification-status.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False))

if __name__=='__main__':run()
